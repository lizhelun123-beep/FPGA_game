`timescale 1ns/1ps

// AXI4-Stream RGB888 white-balance and pixel highlighter.
//
// The RAW pipeline ahead of this block provides demosaic and gamma but no
// usable AWB in RAW(DPC) mode.  The current validation build keeps all three
// channels at unity gain before colour classification.  Two elastic AXI
// register stages preserve all packet sidebands while
// meeting the 142.857 MHz video clock under downstream backpressure.
module axis_color_highlight #(
    parameter integer ENABLE_HIGHLIGHT = 0,
    parameter integer ENABLE_WHITE_BALANCE = 1,
    parameter integer BLUE_MIN_B = 100,
    parameter integer RED_MIN_R = 120,
    parameter integer ORANGE_MIN_R = 140,
    parameter integer ORANGE_MIN_G = 70,
    parameter integer TKEEP_WIDTH = 3,
    parameter integer TUSER_WIDTH = 1
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME ACLK, ASSOCIATED_BUSIF S_AXIS:M_AXIS" *)
    input  wire                         aclk,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TDATA" *)
    input  wire [23:0]                  s_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TVALID" *)
    input  wire                         s_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TREADY" *)
    output wire                         s_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TKEEP" *)
    input  wire [TKEEP_WIDTH-1:0]       s_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TUSER" *)
    input  wire [TUSER_WIDTH-1:0]       s_axis_tuser,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 S_AXIS TLAST" *)
    input  wire                         s_axis_tlast,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TDATA" *)
    output wire [23:0]                  m_axis_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TVALID" *)
    output wire                         m_axis_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TREADY" *)
    input  wire                         m_axis_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TKEEP" *)
    output wire [TKEEP_WIDTH-1:0]       m_axis_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TUSER" *)
    output wire [TUSER_WIDTH-1:0]       m_axis_tuser,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS TLAST" *)
    output wire                         m_axis_tlast
);

    wire [7:0] raw_red   = s_axis_tdata[23:16];
    wire [7:0] raw_green = s_axis_tdata[15:8];
    wire [7:0] raw_blue  = s_axis_tdata[7:0];

    // Unity white-balance validation point: R/G/B = 1.0/1.0/1.0.  Keep this
    // explicit so later grey-card calibration cannot be confused with a Bayer
    // or downstream channel-order correction.
    wire [7:0] balanced_red = raw_red;
    wire [7:0] balanced_blue = raw_blue;

    wire [7:0] input_red = ENABLE_WHITE_BALANCE ? balanced_red : raw_red;
    wire [7:0] input_blue = ENABLE_WHITE_BALANCE ? balanced_blue : raw_blue;
    wire [23:0] corrected_rgb = {input_red, raw_green, input_blue};

    // Xilinx 7-series configuration initializes these valid bits to zero.
    // The module has no independent reset because the surrounding video
    // pipeline remains configured across a PS-only reset.
    reg                         wb_valid = 1'b0;
    reg [23:0]                  wb_data = 24'b0;
    reg [TKEEP_WIDTH-1:0]       wb_keep = {TKEEP_WIDTH{1'b0}};
    reg [TUSER_WIDTH-1:0]       wb_user = {TUSER_WIDTH{1'b0}};
    reg                         wb_last = 1'b0;

    reg                         out_valid = 1'b0;
    reg [23:0]                  out_data = 24'b0;
    reg [TKEEP_WIDTH-1:0]       out_keep = {TKEEP_WIDTH{1'b0}};
    reg [TUSER_WIDTH-1:0]       out_user = {TUSER_WIDTH{1'b0}};
    reg                         out_last = 1'b0;

    wire out_ready = ~out_valid || m_axis_tready;
    wire wb_ready = ~wb_valid || out_ready;

    wire [7:0] red   = wb_data[23:16];
    wire [7:0] green = wb_data[15:8];
    wire [7:0] blue  = wb_data[7:0];

    wire [8:0] red_x2   = {1'b0, red} << 1;
    wire [8:0] green_x2 = {1'b0, green} << 1;
    wire [8:0] blue_x2  = {1'b0, blue} << 1;

    wire blue_hit = (blue >= BLUE_MIN_B) &&
                    (blue_x2 >= (red * 3)) &&
                    (blue_x2 >= (green * 3));

    wire red_hit = (red >= RED_MIN_R) &&
                   (red >= (green * 2)) &&
                   (red >= (blue * 2));

    wire orange_hit = (red >= ORANGE_MIN_R) &&
                      (green >= ORANGE_MIN_G) &&
                      (red > green) &&
                      (green_x2 > red) &&
                      (green >= (blue * 2));

    localparam [23:0] BLUE_HIGHLIGHT   = 24'h0080FF;
    localparam [23:0] RED_HIGHLIGHT    = 24'hFF0000;
    localparam [23:0] ORANGE_HIGHLIGHT = 24'hFF8000;

    wire [23:0] highlighted_rgb = blue_hit   ? BLUE_HIGHLIGHT :
                                  red_hit    ? RED_HIGHLIGHT :
                                  orange_hit ? ORANGE_HIGHLIGHT :
                                               wb_data;

    always @(posedge aclk) begin
        if (wb_ready) begin
            wb_valid <= s_axis_tvalid;
            if (s_axis_tvalid) begin
                wb_data <= corrected_rgb;
                wb_keep <= s_axis_tkeep;
                wb_user <= s_axis_tuser;
                wb_last <= s_axis_tlast;
            end
        end

        if (out_ready) begin
            out_valid <= wb_valid;
            if (wb_valid) begin
                out_data <= ENABLE_HIGHLIGHT ? highlighted_rgb : wb_data;
                out_keep <= wb_keep;
                out_user <= wb_user;
                out_last <= wb_last;
            end
        end
    end

    assign s_axis_tready = wb_ready;
    assign m_axis_tdata = out_data;
    assign m_axis_tvalid = out_valid;
    assign m_axis_tkeep = out_keep;
    assign m_axis_tuser = out_user;
    assign m_axis_tlast = out_last;

endmodule
