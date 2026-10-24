`timescale 1ns/1ps

module tb_axis_vision_features;
    localparam integer FRAME_WIDTH = 20;
    localparam integer FRAME_HEIGHT = 12;
    localparam integer PIXELS = FRAME_WIDTH * FRAME_HEIGHT;
    localparam integer FEATURE_WIDTH = FRAME_WIDTH / 4;
    localparam integer FEATURE_HEIGHT = FRAME_HEIGHT / 4;
    localparam integer FEATURES = FEATURE_WIDTH * FEATURE_HEIGHT;

    reg aclk = 1'b0;
    always #3.5 aclk = ~aclk;

    reg aresetn = 1'b0;
    reg [23:0] s_axis_tdata = 24'b0;
    reg s_axis_tvalid = 1'b0;
    wire s_axis_tready;
    reg [2:0] s_axis_tkeep = 3'b111;
    reg s_axis_tuser = 1'b0;
    reg s_axis_tlast = 1'b0;

    wire [23:0] m_axis_video_tdata;
    wire m_axis_video_tvalid;
    reg m_axis_video_tready = 1'b0;
    wire [2:0] m_axis_video_tkeep;
    wire m_axis_video_tuser;
    wire m_axis_video_tlast;

    wire [31:0] m_axis_feature_tdata;
    wire m_axis_feature_tvalid;
    reg m_axis_feature_tready = 1'b0;
    wire [3:0] m_axis_feature_tkeep;
    wire m_axis_feature_tuser;
    wire m_axis_feature_tlast;

    reg [23:0] pixels [0:PIXELS-1];
    reg [31:0] expected_features [0:FEATURES-1];
    integer video_read = 0;
    integer feature_read = 0;
    integer feature_write = 0;
    integer failures = 0;
    integer cycles = 0;
    integer index;
    integer x;
    integer y;

    axis_vision_features #(
        .FRAME_WIDTH(FRAME_WIDTH),
        .FRAME_HEIGHT(FRAME_HEIGHT)
    ) dut (
        .aclk(aclk),
        .aresetn(aresetn),
        .s_axis_tdata(s_axis_tdata),
        .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready),
        .s_axis_tkeep(s_axis_tkeep),
        .s_axis_tuser(s_axis_tuser),
        .s_axis_tlast(s_axis_tlast),
        .m_axis_video_tdata(m_axis_video_tdata),
        .m_axis_video_tvalid(m_axis_video_tvalid),
        .m_axis_video_tready(m_axis_video_tready),
        .m_axis_video_tkeep(m_axis_video_tkeep),
        .m_axis_video_tuser(m_axis_video_tuser),
        .m_axis_video_tlast(m_axis_video_tlast),
        .m_axis_feature_tdata(m_axis_feature_tdata),
        .m_axis_feature_tvalid(m_axis_feature_tvalid),
        .m_axis_feature_tready(m_axis_feature_tready),
        .m_axis_feature_tkeep(m_axis_feature_tkeep),
        .m_axis_feature_tuser(m_axis_feature_tuser),
        .m_axis_feature_tlast(m_axis_feature_tlast)
    );

    function automatic integer divide_round_nearest;
        input integer numerator;
        input integer denominator;
        begin
            if (numerator >= 0)
                divide_round_nearest = (numerator + denominator / 2) / denominator;
            else
                divide_round_nearest = -((-numerator + denominator / 2) / denominator);
        end
    endfunction

    function automatic [7:0] classify;
        input integer h;
        input integer s;
        input integer v;
        reg [7:0] mask;
        begin
            mask = 8'b0;
            if (h >= 18 && h <= 36 && s >= 85 && v >= 85) mask = mask | 8'h01;
            if (((h >= 60 && h <= 130) &&
                 ((s >= 85 && v >= 45) ||
                  (s >= 5 && s <= 84 && v >= 45 && v <= 170))) ||
                (h >= 14 && h <= 45 && s >= 20 && s <= 100 &&
                 v >= 40 && v <= 60)) mask = mask | 8'h02;
            if (h >= 15 && h <= 21 && s >= 65 && v >= 80) mask = mask | 8'h04;
            if (h >= 37 && h <= 89 && s >= 70 && v >= 45) mask = mask | 8'h08;
            if (h >= 10 && h <= 19 && s >= 120 && v >= 65) mask = mask | 8'h10;
            if (v <= 65) mask = mask | 8'h20;
            if (h <= 60 && s <= 100 && v >= 70) mask = mask | 8'h40;
            if (v <= 60) mask = mask | 8'h80;
            classify = mask;
        end
    endfunction

    function automatic [31:0] reference_feature;
        input [23:0] rgb;
        integer r;
        integer g;
        integer b;
        integer maximum;
        integer minimum;
        integer difference;
        integer hue;
        integer saturation;
        begin
            r = rgb[23:16];
            g = rgb[15:8];
            b = rgb[7:0];
            maximum = r;
            minimum = r;
            if (g > maximum) maximum = g;
            if (b > maximum) maximum = b;
            if (g < minimum) minimum = g;
            if (b < minimum) minimum = b;
            difference = maximum - minimum;
            saturation = maximum ? divide_round_nearest(difference * 255, maximum) : 0;
            if (difference == 0) begin
                hue = 0;
            end else if (maximum == r) begin
                hue = divide_round_nearest(30 * (g - b), difference);
                if (hue < 0) hue = hue + 180;
            end else if (maximum == g) begin
                hue = 60 + divide_round_nearest(30 * (b - r), difference);
            end else begin
                hue = 120 + divide_round_nearest(30 * (r - g), difference);
            end
            if (hue < 0) hue = hue + 180;
            if (hue > 179) hue = hue - 180;
            reference_feature = {maximum[7:0], saturation[7:0], hue[7:0],
                                 classify(hue, saturation, maximum)};
        end
    endfunction

    task automatic fail;
        input [1023:0] message;
        begin
            failures = failures + 1;
            $display("FAIL: %0s", message);
        end
    endtask

    always @(posedge aclk) begin
        if (!aresetn) begin
            cycles <= 0;
            m_axis_video_tready <= 1'b0;
            m_axis_feature_tready <= 1'b0;
        end else begin
            cycles <= cycles + 1;
            // Exercise independent downstream stalls, including a feature
            // stall that spans non-sampled source pixels.
            m_axis_video_tready <= (cycles % 11) != 3;
            m_axis_feature_tready <= (cycles % 13) < 9;

            if (m_axis_video_tvalid && m_axis_video_tready) begin
                if (video_read >= PIXELS) begin
                    fail("extra video beat");
                end else begin
                    if (m_axis_video_tdata !== pixels[video_read])
                        fail("video data changed");
                    if (m_axis_video_tkeep !== 3'b111)
                        fail("video TKEEP changed");
                    if (m_axis_video_tuser !== (video_read == 0))
                        fail("video TUSER misaligned");
                    if (m_axis_video_tlast !== ((video_read % FRAME_WIDTH) == FRAME_WIDTH - 1))
                        fail("video TLAST misaligned");
                end
                video_read = video_read + 1;
            end

            if (m_axis_feature_tvalid && m_axis_feature_tready) begin
                if (feature_read >= FEATURES) begin
                    fail("extra feature beat");
                end else begin
                    if (m_axis_feature_tdata !== expected_features[feature_read]) begin
                        failures = failures + 1;
                        $display("FAIL feature %0d got=%08x expected=%08x",
                                 feature_read, m_axis_feature_tdata,
                                 expected_features[feature_read]);
                    end
                    if (m_axis_feature_tkeep !== 4'b1111)
                        fail("feature TKEEP invalid");
                    if (m_axis_feature_tuser !== (feature_read == 0))
                        fail("feature TUSER misaligned");
                    if (m_axis_feature_tlast !==
                        ((feature_read % FEATURE_WIDTH) == FEATURE_WIDTH - 1))
                        fail("feature TLAST misaligned");
                end
                feature_read = feature_read + 1;
            end
        end
    end

    initial begin
        // Deterministic full-range RGB coverage plus hand-picked HSV boundaries
        // at sampled locations.
        for (index = 0; index < PIXELS; index = index + 1)
            pixels[index] = {((index * 73 + 17) & 8'hff),
                             ((index * 29 + 91) & 8'hff),
                             ((index * 151 + 7) & 8'hff)};

        pixels[1 * FRAME_WIDTH + 1] = 24'hff0000;
        pixels[1 * FRAME_WIDTH + 5] = 24'h00ff00;
        pixels[1 * FRAME_WIDTH + 9] = 24'h0000ff;
        pixels[1 * FRAME_WIDTH + 13] = 24'hffffff;
        pixels[1 * FRAME_WIDTH + 17] = 24'h000000;
        pixels[5 * FRAME_WIDTH + 1] = 24'h965028;
        pixels[5 * FRAME_WIDTH + 5] = 24'h783c00;
        pixels[5 * FRAME_WIDTH + 9] = 24'h646496;
        pixels[5 * FRAME_WIDTH + 13] = 24'h46321e;
        pixels[5 * FRAME_WIDTH + 17] = 24'h808080;

        for (y = 1; y < FRAME_HEIGHT; y = y + 4)
            for (x = 1; x < FRAME_WIDTH; x = x + 4) begin
                expected_features[feature_write] =
                    reference_feature(pixels[y * FRAME_WIDTH + x]);
                feature_write = feature_write + 1;
            end
        if (feature_write != FEATURES)
            $fatal(1, "test feature geometry mismatch");

        repeat (4) @(posedge aclk);
        @(negedge aclk);
        aresetn = 1'b1;

        for (index = 0; index < PIXELS; index = index + 1) begin
            @(negedge aclk);
            s_axis_tdata = pixels[index];
            s_axis_tuser = index == 0;
            s_axis_tlast = (index % FRAME_WIDTH) == FRAME_WIDTH - 1;
            s_axis_tvalid = 1'b1;
            do @(posedge aclk); while (!s_axis_tready);
        end
        @(negedge aclk);
        s_axis_tvalid = 1'b0;
        s_axis_tuser = 1'b0;
        s_axis_tlast = 1'b0;

        while ((video_read < PIXELS || feature_read < FEATURES) && cycles < 2000)
            @(posedge aclk);
        repeat (3) @(posedge aclk);

        if (video_read != PIXELS) begin
            failures = failures + 1;
            $display("FAIL video count got=%0d expected=%0d", video_read, PIXELS);
        end
        if (feature_read != FEATURES) begin
            failures = failures + 1;
            $display("FAIL feature count got=%0d expected=%0d", feature_read, FEATURES);
        end
        $display("axis_vision_features: video=%0d feature=%0d failures=%0d",
                 video_read, feature_read, failures);
        if (failures != 0)
            $fatal(1, "axis_vision_features self-check failed");
        $finish;
    end

endmodule
