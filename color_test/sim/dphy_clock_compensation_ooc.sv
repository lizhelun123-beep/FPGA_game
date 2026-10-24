`timescale 1ns/1ps
// Isolated verification harness; not part of the production block design.
// Reuse the canonical lane deserializer. Historical default: matched BUFGs.
// Budget modes: internal/HPC, matched BUFGs or shared feedback/serial BUFG.
// None is an accepted receiver or a production clock selection.
module dphy_clock_compensation_ooc #(
    // Fixed budget-only probe. Never a production receiver selection.
    parameter integer HPC_INTERNAL_PROBE = 0,
    parameter integer BUFG_FEEDBACK_PROBE = 0,
    // Model-only feedback-family attempt 2: CLKFBOUT drives the SAME BUFG
    // feeding CLKFBIN and serial loads. Not an accepted sampling clock.
    parameter integer SHARED_FB_SERIAL_PROBE = 0,
    // Fixed tap-0 local clock budget; no calibration controller.
    parameter integer LOCAL_CLOCK_PROBE = 0,
    // Different physical CMT primitive: one fixed PLL budget, not an MMCM retry.
    parameter integer PLL_CLOCK_PROBE = 0
) (
    input wire dphy_clk_p, dphy_clk_n,
    input wire [1:0] dphy_data_p, dphy_data_n,
    input wire refclk, request_reset,
    input wire [1:0] dphy_data_lp_p, dphy_data_lp_n,
    input wire dphy_clk_lp_p, dphy_clk_lp_n,
    output wire [3:0] lp_observed,
    output wire [1:0] clock_lp_observed,
    output wire [15:0] data_out,
    output wire [1:0] data_valid,
    output wire ready
);
    wire hs_input, serial_unbuffered, byte_unbuffered, feedback_out, feedback;
    wire mmcm_serial, mmcm_byte, pll_serial, pll_byte, pll_locked;
    wire serial_clk, byte_clk, ctl_clk, locked, mmcm_locked, clock_delay_ready;
    wire mmcm_reset, capture_reset;
    wire [1:0] sync_hard, sync_soft, sync_error;
    localparam integer DIRECT_PROBE = HPC_INTERNAL_PROBE || BUFG_FEEDBACK_PROBE || SHARED_FB_SERIAL_PROBE || LOCAL_CLOCK_PROBE || PLL_CLOCK_PROBE;
    initial if ((HPC_INTERNAL_PROBE + BUFG_FEEDBACK_PROBE + SHARED_FB_SERIAL_PROBE + LOCAL_CLOCK_PROBE + PLL_CLOCK_PROBE) > 1)
        $error("Select exactly one budget topology");
    IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE"), .IOSTANDARD("LVDS_25"))
        clock_input (.I(dphy_clk_p), .IB(dphy_clk_n), .O(hs_input));
    BUFG ref_buffer (.I(refclk), .O(ctl_clk));
    // 280.034 MHz * 3 = 840.101 MHz VCO; output /3 and /12.
    // Do not reuse the unfinished 60 MHz /15 production MMCM branch.
    MMCME2_ADV #(
        .BANDWIDTH("OPTIMIZED"), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(3.0),
        .CLKIN1_PERIOD(3.571), .CLKOUT0_DIVIDE_F(3.0), .CLKOUT1_DIVIDE(12),
        .CLKOUT0_PHASE(DIRECT_PROBE ? 0.0 : 60.0),
        .CLKOUT1_PHASE(DIRECT_PROBE ? 0.0 : 15.0),
        // UG472: leave the declared default; tools select from connectivity.
        .COMPENSATION("ZHOLD"), .REF_JITTER1(0.010)
    ) mmcm (
        .CLKIN1(hs_input), .CLKIN2(1'b0), .CLKINSEL(1'b1),
        .CLKFBIN(feedback), .CLKFBOUT(feedback_out),
        .CLKOUT0(mmcm_serial), .CLKOUT1(mmcm_byte), .LOCKED(mmcm_locked),
        .RST(mmcm_reset), .PWRDWN(1'b0), .DADDR(7'b0), .DCLK(1'b0),
        .DEN(1'b0), .DI(16'b0), .DWE(1'b0), .PSCLK(1'b0), .PSEN(1'b0), .PSINCDEC(1'b0)
    );
    assign serial_unbuffered = PLL_CLOCK_PROBE ? pll_serial : mmcm_serial;
    assign byte_unbuffered = PLL_CLOCK_PROBE ? pll_byte : mmcm_byte;
    assign locked = PLL_CLOCK_PROBE ? pll_locked : (LOCAL_CLOCK_PROBE ? clock_delay_ready : mmcm_locked);
    if (PLL_CLOCK_PROBE) begin : pll_clock
        wire pll_feedback_out, pll_feedback;
        // Remove the unused MMCM; no mixed CMT outputs or non-dedicated clock path.
        assign feedback = feedback_out;
        // 280.034 MHz *4 = 1120.134 MHz; /4 and /16, same -0.89275 ns shift.
        PLLE2_ADV #(.BANDWIDTH("OPTIMIZED"), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT(4),
            .CLKIN1_PERIOD(3.571), .CLKOUT0_DIVIDE(4), .CLKOUT1_DIVIDE(16),
            .CLKOUT0_PHASE(-90.0), .CLKOUT1_PHASE(-22.5),
            .COMPENSATION("ZHOLD"), .REF_JITTER1(0.010)) pll (
            .CLKIN1(hs_input), .CLKIN2(1'b0), .CLKINSEL(1'b1),
            .CLKFBIN(pll_feedback), .CLKFBOUT(pll_feedback_out),
            .CLKOUT0(pll_serial), .CLKOUT1(pll_byte), .LOCKED(pll_locked),
            .RST(mmcm_reset), .PWRDWN(1'b0), .DADDR(7'b0), .DCLK(1'b0),
            .DEN(1'b0), .DI(16'b0), .DWE(1'b0));
        BUFG feedback_buffer (.I(pll_feedback_out), .O(pll_feedback));
        BUFG serial_buffer (.I(serial_unbuffered), .O(serial_clk));
        BUFG byte_buffer (.I(byte_unbuffered), .O(byte_clk));
    end else if (LOCAL_CLOCK_PROBE) begin : local_clock
        wire delayed_clock;
        // Close the unused MMCM loop; all its outputs must optimize away.
        assign feedback = feedback_out;
        IDELAYE2 #(.DELAY_SRC("IDATAIN"), .HIGH_PERFORMANCE_MODE("TRUE"),
            .IDELAY_TYPE("VARIABLE"), .IDELAY_VALUE(0), .REFCLK_FREQUENCY(200.0),
            .SIGNAL_PATTERN("CLOCK"), .CINVCTRL_SEL("FALSE"), .PIPE_SEL("FALSE"))
            clock_delay (.IDATAIN(hs_input), .DATAIN(1'b0), .DATAOUT(delayed_clock),
                .C(ctl_clk), .CE(1'b0), .INC(1'b0), .LD(1'b0), .LDPIPEEN(1'b0),
                .REGRST(1'b0), .CNTVALUEIN(5'b0), .CNTVALUEOUT(), .CINVCTRL(1'b0));
        BUFIO serial_buffer (.I(delayed_clock), .O(serial_clk));
        BUFR #(.BUFR_DIVIDE("4"), .SIM_DEVICE("7SERIES")) byte_buffer (
            .I(delayed_clock), .O(byte_clk), .CE(1'b1), .CLR(request_reset));
    end else if (HPC_INTERNAL_PROBE) begin : hpc
        assign feedback = feedback_out;
        BUFIO serial_buffer (.I(serial_unbuffered), .O(serial_clk));
        BUFR #(.BUFR_DIVIDE("BYPASS"), .SIM_DEVICE("7SERIES"))
            byte_buffer (.I(byte_unbuffered), .O(byte_clk), .CE(1'b1), .CLR(1'b0));
    end else if (SHARED_FB_SERIAL_PROBE) begin : shared_feedback
        BUFG feedback_serial_buffer (.I(feedback_out), .O(feedback));
        assign serial_clk = feedback;
        BUFG byte_buffer (.I(byte_unbuffered), .O(byte_clk));
    end else begin : global_buffers
        BUFG feedback_buffer (.I(feedback_out), .O(feedback));
        BUFG serial_buffer (.I(serial_unbuffered), .O(serial_clk));
        BUFG byte_buffer (.I(byte_unbuffered), .O(byte_clk));
    end
    if (DIRECT_PROBE) begin : clock_lp_inputs
        wire [1:0] clock_lp;
        IBUF clock_lp_p (.I(dphy_clk_lp_p), .O(clock_lp[0]));
        IBUF clock_lp_n (.I(dphy_clk_lp_n), .O(clock_lp[1]));
        (* ASYNC_REG = "TRUE" *) reg [1:0] lp_first, lp_second;
        always @(posedge ctl_clk) begin
            lp_first <= clock_lp;
            lp_second <= lp_first;
        end
        assign clock_lp_observed = lp_second;
    end else begin : historical_lp
        assign clock_lp_observed = 2'b0;
    end
    dphy_mmcm_reset_guard guard (
        .refclk(ctl_clk), .byteclk(byte_clk), .request_reset(request_reset),
        .locked_raw(locked), .mmcm_reset(mmcm_reset), .ready_ref(ready),
        .capture_reset(capture_reset)
    );
    // Timing fixture only: IDELAYCTRL RDY qualification and its startup reset
    // sequencing are outside the guard test; required before production reuse.
    IDELAYCTRL delay_control (.REFCLK(ctl_clk), .RST(request_reset), .RDY(clock_delay_ready));
    for (genvar lane = 0; lane < 2; lane = lane + 1) begin : lanes
        wire hs_data;
        wire [1:0] lp_data;
        if (DIRECT_PROBE) begin : lp_inputs
            IBUF lp_p (.I(dphy_data_lp_p[lane]), .O(lp_data[0]));
            IBUF lp_n (.I(dphy_data_lp_n[lane]), .O(lp_data[1]));
        end else assign lp_data = 2'b0;
        IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE"), .IOSTANDARD("LVDS_25"))
            data_input (.I(dphy_data_p[lane]), .IB(dphy_data_n[lane]), .O(hs_data));
        HS_Deserializer #(.kIs8b9b(0), .kAddDelay_ps(0),
            .kBUFH_DDIRECT_M3(DIRECT_PROBE), .kNoLP(!DIRECT_PROBE)) sampler (
            .dLP0_in(8'b0), .dLP1_in(8'b0), .dLP0_out(), .dLP1_out(),
            .SerClk(serial_clk), .DivClk(byte_clk), .aHSIn(hs_data), .aLPIn(lp_data),
            .aLPOut(lp_observed[lane*2 +: 2]), .dDataOut8(data_out[lane*8 +: 8]), .dDataOut9(),
            .dValid(data_valid[lane]), .dSyncHard(sync_hard[lane]),
            .dSyncSoft(sync_soft[lane]), .dSyncErr(sync_error[lane]),
            .CtlClk(ctl_clk), .cIDLY_LD(1'b0), .cIDLY_CE(1'b0), .cIDLY_INC(1'b0),
            .cIDLY_CNT(), .aRst(capture_reset), .aSettled(1'b1)
        );
    end
endmodule

// Adopted whole-vendor-PHY budget only. Its real HS/LP receivers and PCS/byte
// alignment stay intact. The registered PPI sink retains the byte data load;
// the canonical CSI parser/video, production enable CDC and hold adapter are
// omitted here and must be verified separately if the sampling budget passes.
module dphy_amd_phy_fixed_ooc (
    input wire dphy_clk_p, dphy_clk_n,
    input wire [1:0] dphy_data_p, dphy_data_n,
    input wire dphy_clk_lp_p, dphy_clk_lp_n,
    input wire [1:0] dphy_data_lp_p, dphy_data_lp_n,
    input wire refclk, request_reset, lane_enable,
    input wire [1:0] force_rx,
    output reg [15:0] data_out,
    output wire [1:0] data_valid, data_active, data_sync,
    output wire [15:0] escape_data,
    output wire [7:0] escape_trigger,
    output wire [31:0] status
);
    wire core_clk, byte_clk, delay_ready, init_done, system_reset_out;
    wire clk_active, clk_stop, clk_ulpsnot, clk_rxulpsnot;
    wire [15:0] rxdata;
    wire [1:0] stopstate, ulpsactivenot, escclk, lpdt, ulps, escvalid;
    wire [1:0] errsot, errsotsync, erresc, errsyncesc, errcontrol;
    wire clk_lp_p_buf, clk_lp_n_buf;
    wire [1:0] data_lp_p_buf, data_lp_n_buf;
    // Reuse InputBuffer.vhd's LP-only HSUL_12 receivers. The vendor owns HS
    // IBUFDS; keep each named LP P/N input and lane index unchanged.
    IBUF #(.IOSTANDARD("HSUL_12"), .IBUF_LOW_PWR("TRUE"))
        clock_lp_p_input (.I(dphy_clk_lp_p), .O(clk_lp_p_buf));
    IBUF #(.IOSTANDARD("HSUL_12"), .IBUF_LOW_PWR("TRUE"))
        clock_lp_n_input (.I(dphy_clk_lp_n), .O(clk_lp_n_buf));
    for (genvar lane = 0; lane < 2; lane = lane + 1) begin : lp_input_buffers
        IBUF #(.IOSTANDARD("HSUL_12"), .IBUF_LOW_PWR("TRUE"))
            data_lp_p_input (.I(dphy_data_lp_p[lane]), .O(data_lp_p_buf[lane]));
        IBUF #(.IOSTANDARD("HSUL_12"), .IBUF_LOW_PWR("TRUE"))
            data_lp_n_input (.I(dphy_data_lp_n[lane]), .O(data_lp_n_buf[lane]));
    end
    BUFG reference_buffer (.I(refclk), .O(core_clk));
    IDELAYCTRL delay_control (.REFCLK(core_clk), .RST(request_reset), .RDY(delay_ready));
    amd_fixed_rx phy (
        .core_clk(core_clk), .core_rst(request_reset), .dlyctrl_rdy_in(delay_ready),
        .rxbyteclkhs(byte_clk), .init_done(init_done), .system_rst_out(system_reset_out),
        .cl_enable(lane_enable), .cl_rxclkactivehs(clk_active), .cl_stopstate(clk_stop),
        .cl_ulpsactivenot(clk_ulpsnot), .cl_rxulpsclknot(clk_rxulpsnot),
        .clk_hs_rxp(dphy_clk_p), .clk_hs_rxn(dphy_clk_n),
        .clk_lp_rxp(clk_lp_p_buf), .clk_lp_rxn(clk_lp_n_buf),
        .data_hs_rxp(dphy_data_p), .data_hs_rxn(dphy_data_n),
        .data_lp_rxp(data_lp_p_buf), .data_lp_rxn(data_lp_n_buf),
        .dl0_enable(lane_enable), .dl1_enable(lane_enable),
        .dl0_forcerxmode(force_rx[0]), .dl1_forcerxmode(force_rx[1]),
        .dl0_rxdatahs(rxdata[7:0]), .dl1_rxdatahs(rxdata[15:8]),
        .dl0_rxvalidhs(data_valid[0]), .dl1_rxvalidhs(data_valid[1]),
        .dl0_rxactivehs(data_active[0]), .dl1_rxactivehs(data_active[1]),
        .dl0_rxsynchs(data_sync[0]), .dl1_rxsynchs(data_sync[1]),
        .dl0_stopstate(stopstate[0]), .dl1_stopstate(stopstate[1]),
        .dl0_ulpsactivenot(ulpsactivenot[0]), .dl1_ulpsactivenot(ulpsactivenot[1]),
        .dl0_rxclkesc(escclk[0]), .dl1_rxclkesc(escclk[1]),
        .dl0_rxlpdtesc(lpdt[0]), .dl1_rxlpdtesc(lpdt[1]),
        .dl0_rxulpsesc(ulps[0]), .dl1_rxulpsesc(ulps[1]),
        .dl0_rxvalidesc(escvalid[0]), .dl1_rxvalidesc(escvalid[1]),
        .dl0_rxtriggeresc(escape_trigger[3:0]), .dl1_rxtriggeresc(escape_trigger[7:4]),
        .dl0_rxdataesc(escape_data[7:0]), .dl1_rxdataesc(escape_data[15:8]),
        .dl0_errsoths(errsot[0]), .dl1_errsoths(errsot[1]),
        .dl0_errsotsynchs(errsotsync[0]), .dl1_errsotsynchs(errsotsync[1]),
        .dl0_erresc(erresc[0]), .dl1_erresc(erresc[1]),
        .dl0_errsyncesc(errsyncesc[0]), .dl1_errsyncesc(errsyncesc[1]),
        .dl0_errcontrol(errcontrol[0]), .dl1_errcontrol(errcontrol[1])
    );
    always @(posedge byte_clk) begin
        if (data_valid[0]) data_out[7:0] <= rxdata[7:0];
        if (data_valid[1]) data_out[15:8] <= rxdata[15:8];
    end
    assign status = {3'b0, system_reset_out, init_done, delay_ready,
        clk_active, clk_stop, clk_ulpsnot, clk_rxulpsnot,
        stopstate, ulpsactivenot, escclk, lpdt, ulps, escvalid,
        errsot, errsotsync, erresc, errsyncesc, errcontrol};
endmodule

// Test-only startup/relock controller. All timers use the always-running
// 200 MHz reference, never the clock that may stop. Qualification never relies
// on a fixed lock delay. A latched loss survives even a short LOCKED pulse.
module dphy_mmcm_reset_guard (
    input wire refclk, byteclk, request_reset, locked_raw,
    output reg mmcm_reset = 1'b1,
    output wire ready_ref,
    output wire capture_reset
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] lock_sync = 2'b00;
    reg loss_latched = 1'b1;
    reg lock_seen = 1'b0;
    reg [3:0] reset_left = 4'd8;
    reg [2:0] stable_cycles = 3'd0;
    always @(posedge refclk or negedge locked_raw)
        if (!locked_raw) loss_latched <= 1'b1;
        else if (!lock_seen) loss_latched <= 1'b0;
    always @(posedge refclk or posedge request_reset)
        if (request_reset) lock_sync <= 2'b00;
        else lock_sync <= {lock_sync[0], locked_raw};
    always @(posedge refclk or posedge request_reset) begin
        if (request_reset) begin
            mmcm_reset <= 1'b1;
            reset_left <= 4'd8;
            stable_cycles <= 3'd0;
            lock_seen <= 1'b0;
        end else if (mmcm_reset) begin
            stable_cycles <= 3'd0;
            if (reset_left == 1) begin
                mmcm_reset <= 1'b0;
                reset_left <= 0;
            end else reset_left <= reset_left - 1'b1;
        end else if (lock_seen && loss_latched) begin
            mmcm_reset <= 1'b1;
            reset_left <= 4'd8;
            stable_cycles <= 3'd0;
            lock_seen <= 1'b0;
        end else if (!lock_sync[1] || loss_latched) begin
            stable_cycles <= 3'd0;
        end else if (stable_cycles < 4) begin
            stable_cycles <= stable_cycles + 1'b1;
            if (stable_cycles == 3) lock_seen <= 1'b1;
        end
    end
    assign ready_ref = lock_seen && stable_cycles == 4 && !mmcm_reset && !loss_latched;
    wire capture_hold = request_reset || mmcm_reset || !locked_raw || !ready_ref;
    (* ASYNC_REG = "TRUE" *) reg [1:0] capture_stages = 2'b11;
    always @(posedge byteclk or posedge capture_hold)
        if (capture_hold) capture_stages <= 2'b11;
        else capture_stages <= {capture_stages[0], 1'b0};
    assign capture_reset = capture_stages[1];
endmodule
