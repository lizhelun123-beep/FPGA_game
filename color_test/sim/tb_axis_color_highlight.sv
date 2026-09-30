`timescale 1ns/1ps

module tb_axis_color_highlight;

    reg         aclk = 1'b0;
    always #5 aclk = ~aclk;

    reg  [23:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg  [2:0]  s_axis_tkeep;
    reg         s_axis_tuser;
    reg         s_axis_tlast;
    wire [23:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire [2:0]  m_axis_tkeep;
    wire        m_axis_tuser;
    wire        m_axis_tlast;

    integer checks = 0;
    integer failures = 0;

    axis_color_highlight #(
        // Predicate/sideband checks use bypass so their original boundaries
        // remain independent of the separately checked white-balance stage.
        .ENABLE_WHITE_BALANCE(0)
    ) dut (
        .aclk          (aclk),
        .s_axis_tdata  (s_axis_tdata),
        .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .s_axis_tkeep  (s_axis_tkeep),
        .s_axis_tuser  (s_axis_tuser),
        .s_axis_tlast  (s_axis_tlast),
        .m_axis_tdata  (m_axis_tdata),
        .m_axis_tvalid (m_axis_tvalid),
        .m_axis_tready (m_axis_tready),
        .m_axis_tkeep  (m_axis_tkeep),
        .m_axis_tuser  (m_axis_tuser),
        .m_axis_tlast  (m_axis_tlast)
    );

    task automatic check_output;
        input [23:0] expected;
        input [2:0]  expected_keep;
        input        expected_user;
        input        expected_last;
        begin
            checks = checks + 1;
            if (!m_axis_tvalid || !s_axis_tready ||
                m_axis_tdata !== expected ||
                m_axis_tkeep !== expected_keep ||
                m_axis_tuser !== expected_user ||
                m_axis_tlast !== expected_last) begin
                failures = failures + 1;
                $display("FAIL check %0d: valid=%b ready=%b data=%h keep=%b user=%b last=%b expected=%h/%b/%b/%b",
                         checks, m_axis_tvalid, s_axis_tready, m_axis_tdata,
                         m_axis_tkeep, m_axis_tuser, m_axis_tlast,
                         expected, expected_keep, expected_user, expected_last);
            end
        end
    endtask

    task automatic send_pixel;
        input [23:0] pixel;
        input [23:0] expected;
        begin
            @(negedge aclk);
            s_axis_tdata  = pixel;
            s_axis_tkeep  = 3'b101;
            s_axis_tuser  = 1'b1;
            s_axis_tlast  = 1'b1;
            s_axis_tvalid = 1'b1;
            @(posedge aclk);
            @(negedge aclk);
            s_axis_tvalid = 1'b0;
            s_axis_tlast  = 1'b0;
            s_axis_tuser  = 1'b0;
            @(posedge aclk);
            #1 check_output(expected, 3'b101, 1'b1, 1'b1);
        end
    endtask

    task automatic send_with_backpressure;
        input [23:0] pixel;
        input [23:0] expected;
        begin
            // Drain the preceding full-rate transaction before deliberately
            // blocking the output of this isolated backpressure case.
            @(posedge aclk);
            #1;
            @(negedge aclk);
            s_axis_tdata  = pixel;
            s_axis_tkeep  = 3'b110;
            s_axis_tuser  = 1'b0;
            s_axis_tlast  = 1'b1;
            s_axis_tvalid = 1'b1;
            m_axis_tready = 1'b0;
            @(posedge aclk);
            @(negedge aclk);
            s_axis_tvalid = 1'b0;
            @(posedge aclk);
            #1;
            repeat (3) begin
                checks = checks + 1;
                if (!m_axis_tvalid || m_axis_tdata !== expected ||
                    m_axis_tkeep !== 3'b110 || m_axis_tuser !== 1'b0 ||
                    m_axis_tlast !== 1'b1) begin
                    failures = failures + 1;
                    $display("FAIL backpressure check %0d: valid=%b ready=%b data=%h keep=%b user=%b last=%b",
                             checks, m_axis_tvalid, s_axis_tready, m_axis_tdata,
                             m_axis_tkeep, m_axis_tuser, m_axis_tlast);
                end
                @(posedge aclk);
                #1;
            end
            @(negedge aclk);
            m_axis_tready = 1'b1;
            @(posedge aclk);
            #1;
            checks = checks + 1;
            if (m_axis_tvalid) begin
                failures = failures + 1;
                $display("FAIL output did not drain after backpressure release");
            end
        end
    endtask

    initial begin
        s_axis_tdata  = 24'h0;
        s_axis_tvalid = 1'b0;
        s_axis_tkeep  = 3'b000;
        s_axis_tuser  = 1'b0;
        s_axis_tlast  = 1'b0;
        m_axis_tready = 1'b1;

        // Blue threshold and ratio boundaries.
        send_pixel(24'h000064, 24'h0080FF); // B = 100
        send_pixel(24'h640096, 24'h0080FF); // 2B = 3R boundary
        send_pixel(24'h640095, 24'h640095); // ratio just below boundary

        // Red threshold and ratio boundaries.
        send_pixel(24'h780000, 24'hFF0000); // R = 120
        send_pixel(24'h783C00, 24'hFF0000); // R = 2G boundary
        send_pixel(24'h773C00, 24'h773C00); // R below minimum

        // Orange strict ratio and minimum-channel boundaries.
        send_pixel(24'h965000, 24'hFF8000); // R = 150, G = 80
        send_pixel(24'h965000, 24'hFF8000); // G >= 2B boundary (B = 0)
        send_pixel(24'h964B00, 24'hFF0000); // 2G == R: red predicate wins
        send_pixel(24'h965028, 24'hFF8000); // 2G > R, G = 2B boundary
        send_pixel(24'h964564, 24'h964564); // G below orange minimum

        // Neutral pixels remain unchanged.
        send_pixel(24'h000000, 24'h000000);
        send_pixel(24'hFFFFFF, 24'hFFFFFF);

        // Sidebands and data must remain stable while downstream is stalled.
        send_with_backpressure(24'hFF0000, 24'hFF0000);

        $display("axis_color_highlight: %0d checks, %0d failures", checks, failures);
        if (failures != 0)
            $fatal(1, "axis_color_highlight self-check failed");
        $finish;
    end

endmodule
