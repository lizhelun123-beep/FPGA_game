`timescale 1ns/1ps
// Diagnostic only. No AXI master, DDR writer, video output or automatic calibration.
// GP0 is an AXI3 slave: unsupported addresses/bursts return DECERR, never touch DDR.
module dphy_observer_control #(
    parameter integer SAMPLES = 8192,
    parameter integer WINDOW_CYCLES = 100000,
    parameter integer CAPTURE_TIMEOUT = 100000000
)(
    input wire clk, resetn, byte_clk, idelay_ready,
    input wire [4:0] tap0, tap1,
    input wire [31:0] raw_word,
    output wire delay_reset, sampler_reset, byte_reset,
    output reg [1:0] tap_ce,
    output wire [1:0] tap_inc,
    input wire [31:0] awaddr, input wire [11:0] awid,
    input wire [3:0] awlen, input wire [2:0] awsize,
    input wire [1:0] awburst, input wire awvalid, output wire awready,
    input wire [31:0] wdata, input wire [3:0] wstrb, input wire [11:0] wid,
    input wire wlast, wvalid, output wire wready,
    output reg [11:0] bid, output reg [1:0] bresp,
    output reg bvalid, input wire bready,
    input wire [31:0] araddr, input wire [11:0] arid,
    input wire [3:0] arlen, input wire [2:0] arsize,
    input wire [1:0] arburst, input wire arvalid, output wire arready,
    output reg [31:0] rdata, output reg [11:0] rid,
    output reg [1:0] rresp, output reg rlast,
    output reg rvalid, input wire rready
);
    localparam [31:0] BASE = 32'h43c00000;
    (* ram_style = "block" *) reg [31:0] samples [0:SAMPLES-1];
    reg observe = 0, tap_busy = 0, tap_error = 0;
    reg cap_busy = 0, cap_valid = 0, cap_timeout = 0;
    reg [9:0] target = {5'd12,5'd12}, pending = {5'd12,5'd12};
    reg [6:0] reset_left = 64;
    reg [1:0] tap_phase = 0;
    reg [5:0] tap_steps = 0;
    reg [31:0] timeout_count = 0;
    reg [3:0] clear_wait = 8;
    reg request = 0;
    reg [31:0] window = 0, previous_count = 0, frequency_count = 0;
    wire ready;
    xpm_cdc_single #(.DEST_SYNC_FF(2),.SRC_INPUT_REG(0),.INIT_SYNC_FF(1)) ready_bridge
      (.src_clk(1'b0),.src_in(idelay_ready),.dest_clk(clk),.dest_out(ready));
    // Only registered control-domain requests drive asynchronous reset pins.
    // The local predicate also hides data without waiting for the bridge.
    reg delay_hold = 1, sampler_hold = 1;
    // Missing clock is detected by a complete independent count window;
    // it cannot be detected at the physical instant of the last edge.
    wire clock_missing = frequency_count == 0;
    wire isolate = !resetn || !observe || !ready || tap_busy || delay_reset || clock_missing;
    always @(posedge clk) begin
      delay_hold <= !resetn || reset_left != 0;
      sampler_hold <= isolate;
    end
    assign delay_reset = delay_hold;
    assign sampler_reset = sampler_hold;
    assign tap_inc = 2'b11;

    // A continuously running binary source counter, never reset by a tap/capture.
    // XPM registers Gray code at the source and constrains the synchronizer bus.
    reg [31:0] byte_count = 0;
    reg [1:0] frequency_prescale = 0;
    wire [31:0] byte_count_sync;
    // XPM's lossless Gray monitor requires two stable destination samples after
    // a change. Divide by4 even for a possible70MHz source, then restore units.
    always @(posedge byte_clk) begin
      frequency_prescale<=frequency_prescale+1;
      if (frequency_prescale==3) byte_count <= byte_count + 1;
    end
    xpm_cdc_gray #(.DEST_SYNC_FF(2),.REG_OUTPUT(1),.WIDTH(32),
      .INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1)) frequency_bridge
      (.src_clk(byte_clk),.src_in_bin(byte_count),.dest_clk(clk),.dest_out_bin(byte_count_sync));
    always @(posedge clk) begin
      if (!resetn) begin window<=0; previous_count<=0; frequency_count<=0; end
      else if (window == WINDOW_CYCLES-1) begin
        window<=0; frequency_count<=(byte_count_sync-previous_count)<<2;
        previous_count<=byte_count_sync;
      end else window<=window+1;
    end

    wire capture_reset, request_byte, done, byte_ready;
    reg request_seen = 0, capturing = 0, done_byte = 0, finish_pending = 0;
    reg [$clog2(SAMPLES)-1:0] write_index = 0;
    reg byte_released = 0;
    // The ONLY sampler_hold -> byte_clk reset chain. Four stages also stretch
    // even a short assertion across >=3 full CLKDIV periods on release.
    // Both lane primitive RSTs and the capture FSM consume THIS output.
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) byte_reset_bridge
      (.src_arst(sampler_reset),.dest_clk(byte_clk),.dest_arst(capture_reset));
    assign byte_reset = capture_reset;
    xpm_cdc_single #(.DEST_SYNC_FF(2),.SRC_INPUT_REG(0),.INIT_SYNC_FF(1)) request_bridge
      (.src_clk(1'b0),.src_in(request),.dest_clk(byte_clk),.dest_out(request_byte));
    xpm_cdc_single #(.DEST_SYNC_FF(2),.SRC_INPUT_REG(0),.INIT_SYNC_FF(1)) done_bridge
      (.src_clk(1'b0),.src_in(done_byte),.dest_clk(clk),.dest_out(done));
    // This acknowledgement may assert reset asynchronously; it never drives a
    // RAM address/enable. It goes low even with byte_clk stopped. A new ARM
    // waits for shared reset release, eight full byte edges, and control wait.
    // Edges1..2: ISERDES output invalid; logic reset releases on edge2.
    // Edges3..6: four data-pipeline stages fill; edge7 updates aligned output.
    // Edge8 acknowledges readiness (raw observation, NOT packet/eye validity).
    reg [3:0] warmup = 0;
    always @(posedge byte_clk)
      if (capture_reset) warmup<=0;
      else if (warmup!=8) warmup<=warmup+1;
    always @(posedge byte_clk or posedge capture_reset)
      if (capture_reset) byte_released<=0;
      else if (warmup==7) byte_released<=1;
    xpm_cdc_single #(.DEST_SYNC_FF(2),.SRC_INPUT_REG(0),.INIT_SYNC_FF(1)) released_bridge
      (.src_clk(1'b0),.src_in(byte_released),.dest_clk(clk),.dest_out(byte_ready));
    wire capture_unavailable = isolate || sampler_reset || !byte_ready;
    wire capture_visible = cap_valid && !cap_busy && !capture_unavailable;
    wire arm_ready = !cap_busy && !capture_unavailable && clear_wait==0;
    // RAM controls have only synchronous reset. If reset arrives mid-capture,
    // one last write may occur on the first reset edge; the buffer is hidden,
    // completion is cancelled and a later capture overwrites every location.
    always @(posedge byte_clk) begin
      if (capture_reset || !byte_released) begin
        request_seen<=0; capturing<=0; done_byte<=0; write_index<=0; finish_pending<=0;
      end else if (finish_pending) begin
        // The final RAM write occurred on the PREVIOUS byte-clock edge.
        finish_pending<=0; done_byte<=request_seen;
      end else if (!capturing && request_byte != request_seen) begin
        request_seen<=request_byte; write_index<=0; capturing<=1;
      end else if (capturing) begin
        if (write_index == SAMPLES-1) begin capturing<=0; finish_pending<=1; end
        else write_index<=write_index+1;
      end
    end
    always @(posedge byte_clk)
      if (capturing) samples[write_index] <= raw_word;

    // One AXI write burst at a time, preserving its ID and consuming all beats.
    reg wr_active = 0, wr_bad = 0;
    reg [31:0] wr_address = 0;
    reg [3:0] wr_left = 0;
    assign awready = !wr_active && !bvalid;
    assign wready = wr_active && !bvalid && wid==bid;
    wire write_fire = wvalid && wready;
    wire is_target = wr_address == BASE+32'h10;
    wire is_command = wr_address == BASE+32'h14;
    wire is_enable = wr_address == BASE+32'h24;
    wire command_ok =
      (wdata==1 && !cap_busy && !tap_busy && ready) ||
      (wdata==2 && arm_ready) ||
      wdata==4 || (wdata==8 && !cap_busy && !tap_busy);
    wire write_allowed = !wr_bad && wr_left==0 && wlast && wstrb==4'hf &&
      ((is_target && !cap_busy && !tap_busy && wdata[31:10]==0) ||
       (is_command && command_ok) ||
       (is_enable && wdata[31:1]==0 && (!wdata[0] || (!cap_busy && !tap_busy && ready))));
    always @(posedge clk) begin
      if (!resetn) begin wr_active<=0; bvalid<=0; bresp<=0; bid<=0; wr_bad<=0; end
      else begin
        if (bvalid && bready) bvalid<=0;
        if (awvalid && awready) begin
          wr_active<=1; wr_address<=awaddr; wr_left<=awlen; bid<=awid;
          wr_bad<=awlen!=0 || awsize!=2 || awaddr[1:0]!=0 || awburst>1;
        end
        if (write_fire) begin
          if (wr_left==0) begin
            wr_active<=0; bvalid<=1; bresp<=write_allowed ? 2'b00 : 2'b11;
          end else begin wr_left<=wr_left-1; wr_bad<=1; end
        end
      end
    end

    always @(posedge clk) begin
      tap_ce<=0;
      if (!resetn) begin
        observe<=0; tap_busy<=0; tap_error<=0; cap_busy<=0; cap_valid<=0;
        cap_timeout<=0; reset_left<=64; request<=0; timeout_count<=0;
        target<={5'd12,5'd12}; pending<={5'd12,5'd12}; tap_phase<=0; tap_steps<=0; clear_wait<=8;
      end else begin
        if (reset_left!=0) reset_left<=reset_left-1;
        if (capture_unavailable) begin
          cap_busy<=0; cap_valid<=0; request<=0; clear_wait<=8;
          if (clock_missing && observe && (cap_busy || cap_valid)) begin
            cap_timeout<=1; observe<=0;
          end
        end
        else if (clear_wait!=0) clear_wait<=clear_wait-1;
        if (tap_busy) begin
          if (!ready) begin tap_busy<=0; tap_error<=1; end
          else case(tap_phase)
            0: if ({tap1,tap0}==pending) tap_busy<=0;
               else if (tap_steps==32) begin tap_busy<=0; tap_error<=1; end
               else tap_phase<=1;
            1: begin tap_ce<={tap1!=pending[9:5],tap0!=pending[4:0]}; tap_steps<=tap_steps+1; tap_phase<=2; end
            2: tap_phase<=3;
            3: tap_phase<=0;
          endcase
        end
        // Local isolation and byte-clock release both win over completion.
        if (cap_busy && !capture_unavailable) begin
          if (done==request) begin cap_busy<=0; cap_valid<=1; end
          else if (timeout_count==CAPTURE_TIMEOUT-1) begin
            cap_busy<=0; cap_valid<=0; cap_timeout<=1; observe<=0; request<=0;
          end else timeout_count<=timeout_count+1;
        end
        if (write_fire && write_allowed) begin
          if (is_target) target<=wdata[9:0];
          if (is_enable) begin observe<=wdata[0]; if (!wdata[0]) begin cap_busy<=0;cap_valid<=0;request<=0;end end
          if (is_command) case(wdata)
            1: begin pending<=target; tap_busy<=1; tap_error<=0; tap_phase<=0; tap_steps<=0; cap_valid<=0; end
            2: begin request<=~request; cap_busy<=1; cap_valid<=0; cap_timeout<=0; timeout_count<=0; end
            4: begin observe<=0; cap_busy<=0; cap_valid<=0; request<=0; end
            8: begin reset_left<=64; observe<=0; cap_valid<=0; request<=0; end
          endcase
        end
      end
    end

    function automatic [31:0] reg_value(input [31:0] addr);
      case(addr-BASE)
        'h00: reg_value=32'h44504859;
        'h04: reg_value=32'h00010002;
        'h08: reg_value={23'b0,arm_ready,(frequency_count!=0),cap_timeout,capture_visible,cap_busy,tap_error,tap_busy,observe,ready};
        'h0c: reg_value={22'b0,tap1,tap0};
        'h10: reg_value={22'b0,target};
        'h18: reg_value=frequency_count;
        'h1c: reg_value=WINDOW_CYCLES;
        'h20: reg_value=SAMPLES;
        'h24: reg_value={31'b0,observe};
        'h28: reg_value=200000000;
        'h2c: reg_value=32'h08012801; // raw Q1..Q8, two lanes; format documented in README
        default: reg_value=0;
      endcase
    endfunction
    reg rd_active=0, rd_bad=0;
    reg [31:0] rd_address=0;
    reg [3:0] rd_left=0;
    reg [1:0] rd_delay=0;
    wire mem_selected = rd_address>=BASE+'h10000 && rd_address<BASE+'h10000+SAMPLES*4;
    wire reg_selected = rd_address>=BASE && rd_address<=BASE+'h2c && rd_address[1:0]==0;
    reg [31:0] ram_read=0;
    wire [$clog2(SAMPLES)-1:0] ram_index=rd_address[$clog2(SAMPLES)+1:2];
    always @(posedge clk) ram_read <= samples[ram_index];
    assign arready=!rd_active && !rvalid;
    always @(posedge clk) begin
      if (!resetn) begin rd_active<=0;rvalid<=0;rdata<=0;rlast<=0;rid<=0;rresp<=0; end
      else begin
        if (arvalid && arready) begin
          rd_active<=1;rd_address<=araddr;rd_left<=arlen;rid<=arid;rd_delay<=2;
          rd_bad<=arsize!=2 || araddr[1:0]!=0 || arburst>1 || (arlen!=0 && arburst!=1);
        end
        if (rd_active && !rvalid) begin
          if (rd_delay!=0) rd_delay<=rd_delay-1;
          else begin
            rvalid<=1;rlast<=rd_left==0;
            rresp<=rd_bad || (!mem_selected && !reg_selected) ? 2'b11 :
                    (mem_selected && !capture_visible) ? 2'b10 : 2'b00;
            rdata<=rd_bad ? 0 : mem_selected ? (capture_visible?ram_read:0) : reg_value(rd_address);
          end
        end
        if (rvalid && rready) begin
          rvalid<=0;
          if (rd_left==0) rd_active<=0;
          else begin rd_left<=rd_left-1;rd_address<=rd_address+4;rd_delay<=2; end
        end
      end
    end
    initial begin
      // Vivado warns on initializers in non-net output port declarations.
      // Keep explicit power-up values in the synthesizable initial block.
      tap_ce=0; bid=0; bresp=0; bvalid=0;
      rdata=0; rid=0; rresp=0; rlast=0; rvalid=0;
      if (SAMPLES<16 || (SAMPLES & (SAMPLES-1))!=0) $error("Power-of-two capture depth required");
    end
endmodule
