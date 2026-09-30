`timescale 1ns/1ps

module tb_axis_color_isp;
    reg         aclk = 1'b0;
    always #5 aclk = ~aclk;

    reg  [23:0] s_axis_tdata;
    reg         s_axis_tvalid = 1'b0;
    wire        s_axis_tready;
    reg  [2:0]  s_axis_tkeep = 3'b111;
    reg         s_axis_tuser = 1'b1;
    reg         s_axis_tlast = 1'b1;
    wire [23:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready = 1'b1;
    wire [2:0]  m_axis_tkeep;
    wire        m_axis_tuser;
    wire        m_axis_tlast;

    axis_color_highlight #(
        // Disable highlighting so this bench observes only ISP colour gain.
        .BLUE_MIN_B(256),
        .RED_MIN_R(256),
        .ORANGE_MIN_R(256),
        .ORANGE_MIN_G(256)
    ) dut (
        .aclk(aclk),
        .s_axis_tdata(s_axis_tdata),
        .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready),
        .s_axis_tkeep(s_axis_tkeep),
        .s_axis_tuser(s_axis_tuser),
        .s_axis_tlast(s_axis_tlast),
        .m_axis_tdata(m_axis_tdata),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),
        .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tuser(m_axis_tuser),
        .m_axis_tlast(m_axis_tlast)
    );

    task automatic check;
        input [23:0] pixel;
        input [23:0] expected;
        begin
            @(negedge aclk);
            s_axis_tdata = pixel;
            s_axis_tvalid = 1'b1;
            @(posedge aclk);
            @(negedge aclk);
            s_axis_tvalid = 1'b0;
            @(posedge aclk);
            #1;
            if (m_axis_tdata !== expected || !m_axis_tvalid ||
                !s_axis_tready || m_axis_tkeep !== 3'b111 ||
                !m_axis_tuser || !m_axis_tlast)
                $fatal(1, "ISP mismatch: input=%h output=%h expected=%h",
                       pixel, m_axis_tdata, expected);
        end
    endtask

    initial begin
        check(24'h282828, 24'h3c283c); // R/B 1.5x, G 1.0x
        check(24'h010101, 24'h010101); // integer shift-add result
        check(24'hc864c8, 24'hff64ff); // saturate, never wrap
        $display("axis_color_isp: PASS");
        $finish;
    end
endmodule
