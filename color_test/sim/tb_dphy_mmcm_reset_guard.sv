`timescale 1ns/1ps
module tb_dphy_mmcm_reset_guard;
    reg refclk = 0, byteclk = 0, byte_run = 1;
    reg request_reset = 1, locked_raw = 0;
    wire mmcm_reset, ready_ref, capture_reset;
    integer reset_pulses = 0;
    integer pulses_before;
    realtime reset_start = 0;
    dphy_mmcm_reset_guard dut (.*);
    always #2.5 refclk = ~refclk;
    always #7.142 if (byte_run) byteclk = ~byteclk;
    always @(posedge mmcm_reset) begin
        reset_start = $realtime;
        reset_pulses = reset_pulses + 1;
    end
    always @(negedge mmcm_reset)
        if ($realtime - reset_start < 39.9) $fatal(1, "MMCM reset shorter than 40 ns");
    always @(posedge byteclk) begin
        #0.001;
        if (!capture_reset && (!locked_raw || mmcm_reset || !ready_ref || request_reset))
            $fatal(1, "Capture enabled without qualified lock");
    end
    task automatic expect_blocked;
        #0.1;
        if (!capture_reset) $fatal(1, "Capture not asynchronously blocked");
    endtask
    task automatic qualify_lock;
        locked_raw = 1;
        #300;
        if (mmcm_reset || !ready_ref || capture_reset) $fatal(1, "Qualified lock not released");
    endtask
    initial begin
        #23 request_reset = 0;
        // DS187 maximum lock time is 100 us. This behavioral guard test
        // injects that delay; it does not predict analog MMCM locking time.
        #100000;
        expect_blocked();
        if (mmcm_reset || ready_ref) $fatal(1, "Startup wait must fail closed, without reset loop");
        qualify_lock();
        // Stop the byte clock first: reset assertion must not depend on it.
        pulses_before = reset_pulses;
        byte_run = 0;
        #3.1 locked_raw = 0;
        expect_blocked();
        #100;
        if (reset_pulses != pulses_before + 1) $fatal(1, "Lost lock did not request one MMCM reset");
        #100000;
        if (ready_ref || !capture_reset) $fatal(1, "Stopped-clock wait escaped reset");
        byte_run = 1;
        qualify_lock();
        // A short loss between reference edges must remain latched.
        pulses_before = reset_pulses;
        @(negedge refclk);
        #0.4 locked_raw = 0;
        #0.4 locked_raw = 1;
        #100;
        if (reset_pulses != pulses_before + 1) $fatal(1, "Short lost-lock event was missed");
        // Model a real MMCM losing LOCKED while the guard resets it.
        locked_raw = 0;
        #100000;
        expect_blocked();
        qualify_lock();
        byte_run = 0;
        #1.1 request_reset = 1;
        expect_blocked();
        #2.1 request_reset = 0;
        locked_raw = 0;
        #100;
        byte_run = 1;
        qualify_lock();
        $display("PASS: delayed startup, stopped-clock loss, relock, short loss latch, and warm reset");
        $finish;
    end
    initial begin #400000; $fatal(1, "Reset guard simulation timeout"); end
endmodule
