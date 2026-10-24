`timescale 1ns/1ps

// Streaming RGB888 feature extractor for the hybrid PL/PS vision path.
//
// The video output is a transparent AXI4-Stream pass-through.  One pixel from
// each SAMPLE_STEP x SAMPLE_STEP cell is converted with the same integer HSV
// rounding used by vision_ps.c and emitted as one 32-bit feature word:
//
//   [ 7: 0] class mask, [15:8] H, [23:16] S, [31:24] V
//
// The reciprocal/correction divider is exact for the bounded numerators used
// here.  The multiplication stages are intentionally mapped to DSP48 blocks;
// this replaces repeated Cortex-A9 integer division with deterministic PL work.
module axis_vision_features #(
    parameter integer FRAME_WIDTH = 1280,
    parameter integer FRAME_HEIGHT = 720,
    parameter integer SAMPLE_STEP = 4,
    parameter integer SAMPLE_PHASE_X = 1,
    parameter integer SAMPLE_PHASE_Y = 1,
    parameter integer TKEEP_WIDTH = 3,
    parameter integer TUSER_WIDTH = 1,

    parameter integer YELLOW_H_MIN = 18,
    parameter integer YELLOW_H_MAX = 36,
    parameter integer YELLOW_S_MIN = 85,
    parameter integer YELLOW_V_MIN = 85,
    parameter integer BLUE_H_MIN = 60,
    parameter integer BLUE_H_MAX = 130,
    parameter integer BLUE_S_MIN = 85,
    parameter integer BLUE_V_MIN = 45,
    parameter integer BLUE_WASHED_S_MIN = 5,
    parameter integer BLUE_WASHED_S_MAX = 84,
    parameter integer BLUE_WASHED_V_MAX = 170,
    parameter integer BLUE_SHADOW_H_MIN = 14,
    parameter integer BLUE_SHADOW_H_MAX = 45,
    parameter integer BLUE_SHADOW_S_MIN = 20,
    parameter integer BLUE_SHADOW_S_MAX = 100,
    parameter integer BLUE_SHADOW_V_MIN = 40,
    parameter integer BLUE_SHADOW_V_MAX = 60,
    parameter integer ORANGE_H_MIN = 15,
    parameter integer ORANGE_H_MAX = 21,
    parameter integer ORANGE_S_MIN = 65,
    parameter integer ORANGE_V_MIN = 80,
    parameter integer GREEN_H_MIN = 37,
    parameter integer GREEN_H_MAX = 89,
    parameter integer GREEN_S_MIN = 70,
    parameter integer GREEN_V_MIN = 45,
    parameter integer MAGENTA_H_MIN = 10,
    parameter integer MAGENTA_H_MAX = 19,
    parameter integer MAGENTA_S_MIN = 120,
    parameter integer MAGENTA_V_MIN = 65,
    parameter integer BLACK_V_MAX = 65,
    parameter integer WHITE_H_MAX = 60,
    parameter integer WHITE_S_MAX = 100,
    parameter integer WHITE_V_MIN = 70,
    parameter integer WALL_V_MAX = 60
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME ACLK, ASSOCIATED_BUSIF S_AXIS:M_AXIS_VIDEO:M_AXIS_FEATURE, ASSOCIATED_RESET aresetn" *)
    input  wire                         aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME ARESETN, POLARITY ACTIVE_LOW" *)
    input  wire                         aresetn,

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

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TDATA" *)
    output wire [23:0]                  m_axis_video_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TVALID" *)
    output wire                         m_axis_video_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TREADY" *)
    input  wire                         m_axis_video_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TKEEP" *)
    output wire [TKEEP_WIDTH-1:0]       m_axis_video_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TUSER" *)
    output wire [TUSER_WIDTH-1:0]       m_axis_video_tuser,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_VIDEO TLAST" *)
    output wire                         m_axis_video_tlast,

    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TDATA" *)
    output wire [31:0]                  m_axis_feature_tdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TVALID" *)
    output wire                         m_axis_feature_tvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TREADY" *)
    input  wire                         m_axis_feature_tready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TKEEP" *)
    output wire [3:0]                   m_axis_feature_tkeep,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TUSER" *)
    output wire                         m_axis_feature_tuser,
    (* X_INTERFACE_INFO = "xilinx.com:interface:axis:1.0 M_AXIS_FEATURE TLAST" *)
    output wire                         m_axis_feature_tlast
);

    localparam integer X_BITS = $clog2(FRAME_WIDTH + 1);
    localparam integer Y_BITS = $clog2(FRAME_HEIGHT + 1);
    localparam integer LAST_SAMPLE_X = SAMPLE_PHASE_X +
        ((FRAME_WIDTH - 1 - SAMPLE_PHASE_X) / SAMPLE_STEP) * SAMPLE_STEP;

    localparam [7:0] MASK_YELLOW  = 8'h01;
    localparam [7:0] MASK_BLUE    = 8'h02;
    localparam [7:0] MASK_ORANGE  = 8'h04;
    localparam [7:0] MASK_GREEN   = 8'h08;
    localparam [7:0] MASK_MAGENTA = 8'h10;
    localparam [7:0] MASK_BLACK   = 8'h20;
    localparam [7:0] MASK_WHITE   = 8'h40;
    localparam [7:0] MASK_WALL    = 8'h80;

    // Q16 reciprocal ROM.  For 0 < numerator < 2^16, floor(n*r/2^16)
    // differs from floor(n/d) by at most one when r=floor(2^16/d); the next
    // pipeline stage performs the exact one-step correction.
    (* rom_style = "distributed" *) logic [16:0] reciprocal_q16 [0:255];
    integer reciprocal_index;
    initial begin
        reciprocal_q16[0] = 17'd0;
        for (reciprocal_index = 1; reciprocal_index < 256;
             reciprocal_index = reciprocal_index + 1)
            reciprocal_q16[reciprocal_index] = 17'd65536 / reciprocal_index;
    end

    function automatic [7:0] classify_hsv;
        input [7:0] h;
        input [7:0] s;
        input [7:0] v;
        reg [7:0] mask;
        begin
            mask = 8'b0;
            if (h >= YELLOW_H_MIN && h <= YELLOW_H_MAX &&
                s >= YELLOW_S_MIN && v >= YELLOW_V_MIN)
                mask = mask | MASK_YELLOW;
            if (((h >= BLUE_H_MIN && h <= BLUE_H_MAX) &&
                 ((s >= BLUE_S_MIN && v >= BLUE_V_MIN) ||
                  (s >= BLUE_WASHED_S_MIN && s <= BLUE_WASHED_S_MAX &&
                   v >= BLUE_V_MIN && v <= BLUE_WASHED_V_MAX))) ||
                (h >= BLUE_SHADOW_H_MIN && h <= BLUE_SHADOW_H_MAX &&
                 s >= BLUE_SHADOW_S_MIN && s <= BLUE_SHADOW_S_MAX &&
                 v >= BLUE_SHADOW_V_MIN && v <= BLUE_SHADOW_V_MAX))
                mask = mask | MASK_BLUE;
            if (h >= ORANGE_H_MIN && h <= ORANGE_H_MAX &&
                s >= ORANGE_S_MIN && v >= ORANGE_V_MIN)
                mask = mask | MASK_ORANGE;
            if (h >= GREEN_H_MIN && h <= GREEN_H_MAX &&
                s >= GREEN_S_MIN && v >= GREEN_V_MIN)
                mask = mask | MASK_GREEN;
            if (h >= MAGENTA_H_MIN && h <= MAGENTA_H_MAX &&
                s >= MAGENTA_S_MIN && v >= MAGENTA_V_MIN)
                mask = mask | MASK_MAGENTA;
            if (v <= BLACK_V_MAX)
                mask = mask | MASK_BLACK;
            if (h <= WHITE_H_MAX && s <= WHITE_S_MAX && v >= WHITE_V_MIN)
                mask = mask | MASK_WHITE;
            if (v <= WALL_V_MAX)
                mask = mask | MASK_WALL;
            classify_hsv = mask;
        end
    endfunction

    function automatic [7:0] finish_hue;
        input [6:0] quotient;
        input       negative;
        input [7:0] base;
        input       difference_zero;
        integer signed hue_value;
        begin
            if (difference_zero) begin
                finish_hue = 8'd0;
            end else begin
                hue_value = base + (negative ? -$signed({1'b0, quotient}) :
                                                $signed({1'b0, quotient}));
                if (hue_value < 0)
                    hue_value = hue_value + 180;
                if (hue_value > 179)
                    hue_value = hue_value - 180;
                finish_hue = hue_value[7:0];
            end
        end
    endfunction

    reg [X_BITS-1:0] x_count;
    reg [Y_BITS-1:0] y_count;

    wire [X_BITS-1:0] pixel_x = s_axis_tuser[0] ? {X_BITS{1'b0}} : x_count;
    wire [Y_BITS-1:0] pixel_y = s_axis_tuser[0] ? {Y_BITS{1'b0}} : y_count;
    wire sample_candidate = s_axis_tvalid &&
        (pixel_x % SAMPLE_STEP == SAMPLE_PHASE_X) &&
        (pixel_y % SAMPLE_STEP == SAMPLE_PHASE_Y);

    reg                         video_valid;
    reg [23:0]                  video_data;
    reg [TKEEP_WIDTH-1:0]       video_keep;
    reg [TUSER_WIDTH-1:0]       video_user;
    reg                         video_last;
    wire video_ready = ~video_valid || m_axis_video_tready;

    reg         f0_valid;
    reg [15:0]  f0_s_numerator;
    reg [15:0]  f0_h_numerator;
    reg [7:0]   f0_s_denominator;
    reg [7:0]   f0_h_denominator;
    reg [16:0]  f0_s_reciprocal;
    reg [16:0]  f0_h_reciprocal;
    reg [7:0]   f0_value;
    reg [7:0]   f0_hue_base;
    reg         f0_hue_negative;
    reg         f0_user;
    reg         f0_last;

    reg         f1_valid;
    (* use_dsp = "yes" *) reg [32:0] f1_s_product;
    (* use_dsp = "yes" *) reg [32:0] f1_h_product;
    reg [15:0]  f1_s_numerator;
    reg [15:0]  f1_h_numerator;
    reg [7:0]   f1_s_denominator;
    reg [7:0]   f1_h_denominator;
    reg [7:0]   f1_value;
    reg [7:0]   f1_hue_base;
    reg         f1_hue_negative;
    reg         f1_user;
    reg         f1_last;

    wire [16:0] f1_s_q0 = f1_s_product[32:16];
    wire [16:0] f1_h_q0 = f1_h_product[32:16];

    reg         f2_valid;
    reg [16:0]  f2_s_q0;
    reg [16:0]  f2_h_q0;
    (* use_dsp = "yes" *) reg [24:0] f2_s_next_product;
    (* use_dsp = "yes" *) reg [24:0] f2_h_next_product;
    reg [15:0]  f2_s_numerator;
    reg [15:0]  f2_h_numerator;
    reg [7:0]   f2_s_denominator;
    reg [7:0]   f2_h_denominator;
    reg [7:0]   f2_value;
    reg [7:0]   f2_hue_base;
    reg         f2_hue_negative;
    reg         f2_user;
    reg         f2_last;

    reg         f3_valid;
    reg [16:0]  f3_s_quotient;
    reg [16:0]  f3_h_quotient;
    reg [7:0]   f3_value;
    reg [7:0]   f3_hue_base;
    reg         f3_hue_negative;
    reg         f3_difference_zero;
    reg         f3_user;
    reg         f3_last;

    reg         f4_valid;
    reg [7:0]   f4_hue;
    reg [7:0]   f4_saturation;
    reg [7:0]   f4_value;
    reg         f4_user;
    reg         f4_last;

    reg         f5_valid;
    reg [31:0]  f5_data;
    reg         f5_user;
    reg         f5_last;
    wire [7:0] f4_mask = classify_hsv(f4_hue, f4_saturation, f4_value);
    wire feature_pipe_ce = ~f5_valid || m_axis_feature_tready;

    wire input_ready = video_ready && (!sample_candidate || feature_pipe_ce);
    wire input_fire = s_axis_tvalid && input_ready;

    reg [7:0] maximum;
    reg [7:0] minimum;
    reg [7:0] difference;
    reg signed [8:0] hue_delta;
    reg [8:0] hue_delta_abs;
    reg [7:0] hue_base;
    reg hue_negative;
    wire [7:0] input_red = s_axis_tdata[23:16];
    wire [7:0] input_green = s_axis_tdata[15:8];
    wire [7:0] input_blue = s_axis_tdata[7:0];

    always @* begin
        maximum = input_red;
        minimum = input_red;
        if (input_green > maximum) maximum = input_green;
        if (input_blue > maximum) maximum = input_blue;
        if (input_green < minimum) minimum = input_green;
        if (input_blue < minimum) minimum = input_blue;
        difference = maximum - minimum;

        if (maximum == input_red) begin
            hue_delta = $signed({1'b0, input_green}) -
                        $signed({1'b0, input_blue});
            hue_base = 8'd0;
        end else if (maximum == input_green) begin
            hue_delta = $signed({1'b0, input_blue}) -
                        $signed({1'b0, input_red});
            hue_base = 8'd60;
        end else begin
            hue_delta = $signed({1'b0, input_red}) -
                        $signed({1'b0, input_green});
            hue_base = 8'd120;
        end
        hue_negative = hue_delta < 0;
        hue_delta_abs = hue_negative ? -hue_delta : hue_delta;
    end

    always @(posedge aclk) begin
        if (!aresetn) begin
            x_count <= {X_BITS{1'b0}};
            y_count <= {Y_BITS{1'b0}};
            video_valid <= 1'b0;
            f0_valid <= 1'b0;
            f1_valid <= 1'b0;
            f2_valid <= 1'b0;
            f3_valid <= 1'b0;
            f4_valid <= 1'b0;
            f5_valid <= 1'b0;
        end else begin
            if (video_ready) begin
                video_valid <= input_fire;
                if (input_fire) begin
                    video_data <= s_axis_tdata;
                    video_keep <= s_axis_tkeep;
                    video_user <= s_axis_tuser;
                    video_last <= s_axis_tlast;
                end
            end

            if (input_fire) begin
                if (s_axis_tuser[0]) begin
                    x_count <= s_axis_tlast ? {X_BITS{1'b0}} : {{(X_BITS-1){1'b0}}, 1'b1};
                    y_count <= s_axis_tlast ? {{(Y_BITS-1){1'b0}}, 1'b1} : {Y_BITS{1'b0}};
                end else if (s_axis_tlast) begin
                    x_count <= {X_BITS{1'b0}};
                    y_count <= y_count + 1'b1;
                end else begin
                    x_count <= x_count + 1'b1;
                end
            end

            if (feature_pipe_ce) begin
                f0_valid <= input_fire && sample_candidate;
                if (input_fire && sample_candidate) begin
                    f0_s_numerator <= ({8'b0, difference} << 8) - difference +
                                      ({8'b0, maximum} >> 1);
                    f0_h_numerator <= ({7'b0, hue_delta_abs} << 5) -
                                      ({7'b0, hue_delta_abs} << 1) +
                                      ({8'b0, difference} >> 1);
                    f0_s_denominator <= maximum;
                    f0_h_denominator <= difference;
                    f0_s_reciprocal <= reciprocal_q16[maximum];
                    f0_h_reciprocal <= reciprocal_q16[difference];
                    f0_value <= maximum;
                    f0_hue_base <= hue_base;
                    f0_hue_negative <= hue_negative;
                    f0_user <= (pixel_x == SAMPLE_PHASE_X) &&
                               (pixel_y == SAMPLE_PHASE_Y);
                    f0_last <= pixel_x == LAST_SAMPLE_X;
                end

                f1_valid <= f0_valid;
                if (f0_valid) begin
                    f1_s_product <= f0_s_numerator * f0_s_reciprocal;
                    f1_h_product <= f0_h_numerator * f0_h_reciprocal;
                    f1_s_numerator <= f0_s_numerator;
                    f1_h_numerator <= f0_h_numerator;
                    f1_s_denominator <= f0_s_denominator;
                    f1_h_denominator <= f0_h_denominator;
                    f1_value <= f0_value;
                    f1_hue_base <= f0_hue_base;
                    f1_hue_negative <= f0_hue_negative;
                    f1_user <= f0_user;
                    f1_last <= f0_last;
                end

                f2_valid <= f1_valid;
                if (f1_valid) begin
                    f2_s_q0 <= f1_s_q0;
                    f2_h_q0 <= f1_h_q0;
                    f2_s_next_product <= (f1_s_q0 + 1'b1) * f1_s_denominator;
                    f2_h_next_product <= (f1_h_q0 + 1'b1) * f1_h_denominator;
                    f2_s_numerator <= f1_s_numerator;
                    f2_h_numerator <= f1_h_numerator;
                    f2_s_denominator <= f1_s_denominator;
                    f2_h_denominator <= f1_h_denominator;
                    f2_value <= f1_value;
                    f2_hue_base <= f1_hue_base;
                    f2_hue_negative <= f1_hue_negative;
                    f2_user <= f1_user;
                    f2_last <= f1_last;
                end

                f3_valid <= f2_valid;
                if (f2_valid) begin
                    f3_s_quotient <= f2_s_q0 +
                        ((f2_s_denominator != 0 &&
                          f2_s_next_product <= f2_s_numerator) ? 1'b1 : 1'b0);
                    f3_h_quotient <= f2_h_q0 +
                        ((f2_h_denominator != 0 &&
                          f2_h_next_product <= f2_h_numerator) ? 1'b1 : 1'b0);
                    f3_value <= f2_value;
                    f3_hue_base <= f2_hue_base;
                    f3_hue_negative <= f2_hue_negative;
                    f3_difference_zero <= f2_h_denominator == 0;
                    f3_user <= f2_user;
                    f3_last <= f2_last;
                end

                f4_valid <= f3_valid;
                if (f3_valid) begin
                    f4_hue <= finish_hue(f3_h_quotient[6:0],
                                         f3_hue_negative, f3_hue_base,
                                         f3_difference_zero);
                    f4_saturation <= f3_s_quotient[7:0];
                    f4_value <= f3_value;
                    f4_user <= f3_user;
                    f4_last <= f3_last;
                end

                f5_valid <= f4_valid;
                if (f4_valid) begin
                    f5_data <= {f4_value, f4_saturation, f4_hue, f4_mask};
                    f5_user <= f4_user;
                    f5_last <= f4_last;
                end
            end
        end
    end

    assign s_axis_tready = input_ready;
    assign m_axis_video_tdata = video_data;
    assign m_axis_video_tvalid = video_valid;
    assign m_axis_video_tkeep = video_keep;
    assign m_axis_video_tuser = video_user;
    assign m_axis_video_tlast = video_last;

    assign m_axis_feature_tdata = f5_data;
    assign m_axis_feature_tvalid = f5_valid;
    assign m_axis_feature_tkeep = 4'b1111;
    assign m_axis_feature_tuser = f5_user;
    assign m_axis_feature_tlast = f5_last;

endmodule
