`timescale 1ns/1ps
module tb_dphy_observer;
  // Overlay load into a running PS: no artificial external reset pulse at t0.
  reg clk=0, refclk=0, byte_enable=1, resetn=1, lost=0;
  reg serclk=0, use_real_samples=0, lane_bit=1;
  // One oscillator, then the actual integer divider used by the diagnostic.
  // At1ps precision: serial periods7.142/3.572ns, byte28.568/14.288ns.
  real serial_half=3.571;
  wire byteclk;
  always #5 clk=~clk;
  always #2.5 refclk=~refclk;
  always #(serial_half) serclk=byte_enable ? ~serclk : 0;
  wire ready,delay_reset,sampler_reset,byte_reset;
  BUFR #(.BUFR_DIVIDE("4"),.SIM_DEVICE("7SERIES")) byte_divider
    (.I(serclk),.O(byteclk),.CE(1'b1),.CLR(delay_reset));
  wire [4:0] tap0,tap1; wire [1:0] ce,inc;
  reg [31:0] raw_word=32'h32100000;
  always @(posedge byteclk) raw_word<=raw_word+1;
  wire [15:0] serial_raw;
  wire [2:0] serial_valid,serial_hard,serial_soft,serial_error;
  wire [7:0] default_raw;
  // Same raw/metadata packing as the diagnostic top. Soft matches are evidence,
  // not a reason to suppress a completed raw capture.
  wire [31:0] actual_raw_word={4'b0,
    serial_valid[1],serial_error[1],serial_soft[1],serial_hard[1],
    serial_valid[0],serial_error[0],serial_soft[0],serial_hard[0],4'b0,serial_raw};
  // Two actual canonical lanes consume the SAME bridge output. The third
  // instance leaves the new generic omitted, exercising the production default.
  for(genvar lane=0;lane<2;lane=lane+1) begin: real_lanes
    HS_Deserializer #(.kNoLP(1),.kExternalByteReset(1)) sampler
      (.SerClk(serclk),.DivClk(byteclk),.aHSIn(lane==1 ? !lane_bit : lane_bit),
       .aLPIn(2'b0),.aLPOut(),.dLP0_in(8'b0),.dLP1_in(8'b0),.dLP0_out(),.dLP1_out(),
       .dDataOut8(),.dRawDataOut8(serial_raw[8*lane+:8]),.dDataOut9(),
       .dValid(serial_valid[lane]),.dSyncHard(serial_hard[lane]),.dSyncSoft(serial_soft[lane]),
       .dSyncErr(serial_error[lane]),.CtlClk(clk),.cIDLY_LD(1'b0),.cIDLY_CE(1'b0),
       .cIDLY_INC(1'b1),.cIDLY_CNT(),.aRst(byte_reset),.aSettled(1'b1));
  end
  HS_Deserializer #(.kNoLP(1)) default_sampler
    (.SerClk(serclk),.DivClk(byteclk),.aHSIn(lane_bit),.aLPIn(2'b0),.aLPOut(),
     .dLP0_in(8'b0),.dLP1_in(8'b0),.dLP0_out(),.dLP1_out(),
     .dDataOut8(),.dRawDataOut8(default_raw),.dDataOut9(),.dValid(serial_valid[2]),
     .dSyncHard(serial_hard[2]),.dSyncSoft(serial_soft[2]),.dSyncErr(serial_error[2]),
     .CtlClk(clk),.cIDLY_LD(1'b0),.cIDLY_CE(1'b0),.cIDLY_INC(1'b1),.cIDLY_CNT(),
     .aRst(sampler_reset),.aSettled(1'b1));
  IDELAYCTRL calibration(.REFCLK(refclk),.RST(delay_reset),.RDY(ready));
  IDELAYE2 #(.IDELAY_TYPE("VARIABLE"),.IDELAY_VALUE(12),.REFCLK_FREQUENCY(200.0)) d0
    (.C(clk),.CE(ce[0]),.INC(inc[0]),.CNTVALUEOUT(tap0),.LD(1'b0),.LDPIPEEN(1'b0),
     .REGRST(1'b0),.CNTVALUEIN(5'b0),.CINVCTRL(1'b0),.IDATAIN(1'b0),.DATAIN(1'b0),.DATAOUT());
  IDELAYE2 #(.IDELAY_TYPE("VARIABLE"),.IDELAY_VALUE(12),.REFCLK_FREQUENCY(200.0)) d1
    (.C(clk),.CE(ce[1]),.INC(inc[1]),.CNTVALUEOUT(tap1),.LD(1'b0),.LDPIPEEN(1'b0),
     .REGRST(1'b0),.CNTVALUEIN(5'b0),.CINVCTRL(1'b0),.IDATAIN(1'b0),.DATAIN(1'b0),.DATAOUT());
  reg [31:0] awaddr=0,wdata=0,araddr=0;
  reg [11:0] awid=12'h25,wid=12'h25,arid=12'h39;
  reg [3:0] awlen=0,arlen=0,wstrb=15;
  reg [2:0] awsize=2,arsize=2;
  reg [1:0] awburst=1,arburst=1;
  reg awvalid=0,wvalid=0,wlast=1,bready=0,arvalid=0,rready=0;
  wire awready,wready,bvalid,arready,rvalid,rlast;
  wire [1:0] bresp,rresp;wire [11:0] bid,rid;wire [31:0] rdata;
  dphy_observer_control #(.SAMPLES(32),.WINDOW_CYCLES(100),.CAPTURE_TIMEOUT(1000)) dut
    (.clk(clk),.resetn(resetn),.byte_clk(byteclk),.idelay_ready(ready&&!lost),.tap0(tap0),.tap1(tap1),
     .raw_word(use_real_samples ? actual_raw_word : raw_word),.delay_reset(delay_reset),
     .sampler_reset(sampler_reset),.byte_reset(byte_reset),.tap_ce(ce),.tap_inc(inc),
     .awaddr(awaddr),.awid(awid),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),
     .wdata(wdata),.wstrb(wstrb),.wid(wid),.wlast(wlast),.wvalid(wvalid),.wready(wready),
     .bid(bid),.bresp(bresp),.bvalid(bvalid),.bready(bready),
     .araddr(araddr),.arid(arid),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),
     .rdata(rdata),.rid(rid),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready));
  localparam [31:0] B=32'h43c00000;
  integer checks=0;
  task snapshot(input string why);
    $display("DIAG_STATE time=%t reason=%s RAW=%h defaultRaw=%h H=%b S=%b E=%b V=%b",
      $time,why,serial_raw,default_raw,serial_hard,serial_soft,serial_error,serial_valid);
    $display("DIAG_RESET resetn=%b RDY=%b lost=%b hold=%b shared=%b warmup=%0d released=%b ack=%b arm=%b",
      resetn,ready,lost,sampler_reset,byte_reset,dut.warmup,dut.byte_released,dut.byte_ready,dut.arm_ready);
    $display("DIAG_CAPTURE observe=%b busy=%b valid=%b visible=%b capturing=%b index=%0d finish=%b req=%b reqSeen=%b done=%b timeout=%b taps=%0d/%0d freqCount=%0d",
      dut.observe,dut.cap_busy,dut.cap_valid,dut.capture_visible,dut.capturing,dut.write_index,
      dut.finish_pending,dut.request,dut.request_seen,dut.done_byte,dut.cap_timeout,tap0,tap1,dut.frequency_count);
  endtask
  task check(input bit ok,input string why);
    if(!ok) begin snapshot(why);$fatal(1,"FAIL %s at %t",why,$time);end
    checks=checks+1;
  endtask
  integer released_edges=0;
  integer serial_rises=0,last_serial_rises=0;
  reg initial_byte_edge=1;
  reg [31:0] previous_source_count=0;
  always @(posedge serclk) serial_rises=serial_rises+1;
  always @(posedge byteclk) begin
    if(initial_byte_edge) begin
      $display("INITIAL_BYTE_EDGE time_ps=%0.0f binary=%h GSR=%b",$realtime*1000.0,dut.byte_count,glbl.GSR);
      check(dut.byte_count===32'b0,"first source clock starts from known counter INIT0");
      initial_byte_edge=0;
    end else check(dut.byte_count==previous_source_count || dut.byte_count==previous_source_count+1,
                   "independent source monitor permits only hold or unit increment, including recovery");
    previous_source_count=dut.byte_count;
    #0.001;
    if(dut.byte_released && !byte_reset)
      check(serial_rises-last_serial_rises==4,"byte clock has exactly four serial rising edges per full cycle");
    last_serial_rises=serial_rises;
  end
  always @(posedge byteclk or posedge byte_reset) begin
    if(byte_reset) released_edges=0;
    else begin
      released_edges=released_edges+1;
      #0.001;
      check(dut.byte_released==(released_edges>=8),"shared release ack occurs only after eight byte edges");
      if(dut.capturing) check(released_edges>=8,"no RAM capture before deserializer/pipeline warmup");
    end
  end
  task wr(input [31:0] address,input [31:0] value,input [1:0] response=0);
    @(negedge clk);awaddr=address;awvalid=1;wdata=value;wvalid=1;
    do @(posedge clk); while(!awready);
    @(negedge clk);awvalid=0;
    do @(posedge clk); while(!wready);
    @(negedge clk);wvalid=0;
    wait(bvalid);check(bresp===response && bid===awid,"AXI write response/ID");
    repeat(3) begin @(posedge clk);check(bvalid && bid===awid,"write response held under backpressure");end
    @(negedge clk);bready=1;@(posedge clk);@(negedge clk);bready=0;
  endtask
  task rd(input [31:0] address,output [31:0] value,input [1:0] response=0);
    @(negedge clk);araddr=address;arvalid=1;arlen=0;
    do @(posedge clk);while(!arready);
    @(negedge clk);arvalid=0;
    wait(rvalid);value=rdata;
    check(rresp===response && rid===arid && rlast,"AXI read response/ID/last");
    repeat(3)begin @(posedge clk);check(rvalid && rdata===value,"read held under backpressure");end
    @(negedge clk);rready=1;@(posedge clk);@(negedge clk);rready=0;
  endtask
  task poll(input integer bitno,input bit value);
    reg [31:0] status;integer i;
    begin: waiting
      for(i=0;i<100;i=i+1)begin rd(B+8,status);if(status[bitno]===value)disable waiting;end
      snapshot($sformatf("status timeout bit%0d",bitno));$fatal(1,"status timeout bit%0d",bitno);
    end
  endtask
  reg [31:0] v,first,previous;
  realtime reset_asserted;
  integer i;
  task arm;
    wr(B+'h24,1);poll(8,1);wr(B+'h14,2);
  endtask
  task full_capture;
    poll(5,1);rd(B+'h10000,first);
    for(integer k=1;k<32;k=k+1) begin
      rd(B+'h10000+4*k,v);check(v==first+k,"every RAM location replaced in sample order");
    end
  endtask
  task abort_hidden;
    wr(B+'h14,4);rd(B+8,v);check(!v[1]&&!v[5]&&!v[8],"abort hides data and disarms");
    rd(B+'h10000,v,2);check(v==0,"isolated memory response is zero");
  endtask
  initial begin
    #110;
    check(resetn && delay_reset && sampler_reset,"running PS overlay starts isolated without external reset");
    poll(0,1);
    rd(B,v);check(v==32'h44504859,"diagnostic identity");
    rd(B+4,v);check(v==32'h00010002,"API1.2");
    rd(B+'h10000,v,2);check(v==0,"uncommitted memory hidden");
    rd(32'h43000000,v,3);
    wr(B+'h14,2,3); // Cannot arm without explicit observation enable.
    wr(B+'h10,{22'b0,5'd31,5'd0});wr(B+'h14,1);poll(2,0);
    rd(B+'hc,v);check(v[9:0]=={5'd31,5'd0},"actual UNISIM tap wrap/readback");
    wr(B+'h10,{22'b0,5'd24,5'd10});wr(B+'h14,1);poll(2,0);
    rd(B+'hc,v);check(v[9:0]=={5'd24,5'd10},"nominal diagnostic targets read back");
    wstrb=3;wr(B+'h10,0,3);wstrb=15;
    rd(B+'h10,v);check(v[9:0]=={5'd24,5'd10},"rejected partial write changed nothing");
    $display("CASE_PASS overlay_startup_and_actual_taps");
    wr(B+'h24,1);poll(8,1);
    wr(B+'h14,2);rd(B+8,v);check(v[4]&&!v[5],"capture cannot complete before samples");
    wr(B+'h10,0,3); // A capture owns the memory and tap setting.
    poll(5,1);rd(B+'h10000,first);
    for(i=1;i<8;i=i+1)begin rd(B+'h10000+4*i,v);check(v==first+i,"dual-clock samples retain order");end
    repeat(10)@(posedge clk);rd(B+'h10000,v);check(v==first,"completed capture immutable");
    // A second toggle must not accept the previous completion.
    wr(B+'h14,2);rd(B+8,v);check(v[4]&&!v[5],"second capture uses a fresh completion");poll(5,1);
    // Incrementing burst read, including ID, last and backpressure.
    @(negedge clk);araddr=B+'h10000;arlen=3;arvalid=1;
    do @(posedge clk);while(!arready);@(negedge clk);arvalid=0;
    for(i=0;i<4;i=i+1)begin
      wait(rvalid);check(rresp==0&&rid==arid&&rlast==(i==3),"read burst metadata");
      if(i!=0)check(rdata==previous+1,"read burst sample order");previous=rdata;
      @(negedge clk);rready=1;@(posedge clk);@(negedge clk);rready=0;
    end
    arlen=0;
    repeat(500)@(posedge clk);rd(B+'h18,v);check(v>=32&&v<=36,"independent 35MHz count with4-cycle quantization");
    byte_enable=0;repeat(300)@(posedge clk);rd(B+'h18,v);check(v==0,"stopped byte clock detected");
    wr(B+'h14,2,3);rd(B+8,v);
    check(v[6]&&!v[4]&&!v[5]&&!v[1]&&!v[8],"clock watchdog hides completed data, disables observation and refuses ARM");
    rd(B+'h10000,v,2);
    byte_enable=1;wr(B+'h24,1);repeat(20)@(posedge clk);
    wr(B+'h10,{22'b0,5'd12,5'd12});wr(B+'h14,1);poll(2,0);
    poll(8,1);wr(B+'h14,2);rd(B+8,v);check(v[4]&&!v[5],"tap reset cannot cause stale completion");poll(5,1);
    wr(B+'h14,4);rd(B+8,v);check(!v[1]&&!v[5],"explicit abort leaves sampler isolated");
    $display("CASE_PASS baseline_axi_taps_frequency_timeout");
    $display("CASE_PASS clock_loss_hides_completed_buffer");

    // Independent completion-link fault with byte clock still running. Keep
    // the original CAPTURE_TIMEOUT contract covered in addition to watchdog.
    arm();force dut.done=1'b0;
    repeat(1002)@(posedge clk);rd(B+8,v);
    check(v[6]&&!v[4]&&!v[5]&&!v[1],"configured1000-cycle completion timeout fails closed");
    release dut.done;abort_hidden();
    $display("CASE_PASS configured_capture_timeout");

    // Cancelling either final write or the following notification must not
    // publish a partial/old buffer. Force only the bridge output for the two
    // exact priority cases; real RDY loss and host abort are tested below.
    for(i=0;i<2;i=i+1)begin
      arm();
      if(i==0) wait(dut.capturing && dut.write_index==31);
      else wait(dut.finish_pending);
      @(negedge byteclk);force dut.capture_reset=1'b1;
      @(posedge byteclk);#1;
      check(!dut.done_byte&&!dut.finish_pending,"reset cancels last-write/pending notification");
      abort_hidden();release dut.capture_reset;
      arm();full_capture();abort_hidden();
    end
    $display("CASE_PASS reset_at_last_write_and_completion");

    arm();wait(dut.finish_pending);lost=1;
    repeat(12)@(posedge clk);rd(B+8,v);
    check(!v[0]&&!v[5]&&!v[8],"RDY loss wins over a coincident completion");
    rd(B+'h10000,v,2);check(v==0,"RDY loss hides memory");
    lost=0;abort_hidden();arm();full_capture();
    $display("CASE_PASS loss_and_full_rewrite");

    // Preserve an old done=1 while byte_clk is stopped. Synchronous RAM reset
    // cannot run until clock resumes, so ARM must wait for release ack.
    check(dut.done_byte==1,"old completion deliberately present before stopped-clock reset");
    previous=first;byte_enable=0;repeat(4)@(posedge clk);
    abort_hidden();wr(B+'h24,1);repeat(24)@(posedge clk);rd(B+8,v);
    check(!v[8]&&!v[5],"stopped clock cannot acknowledge reset release");
    wr(B+'h14,2,3);rd(B+'h10000,v,2);
    byte_enable=1;poll(8,1);wr(B+'h14,2);full_capture();
    check(first!=previous,"new complete buffer differs from old generation");
    wr(B+'h14,2);full_capture();
    $display("CASE_PASS stopped_disable_enable_and_continuous_capture");

    // A committed AXI response cannot be withdrawn on abort; later reads hide.
    @(negedge clk);araddr=B+'h10000;arlen=0;arvalid=1;
    do @(posedge clk);while(!arready);@(negedge clk);arvalid=0;
    wait(rvalid);previous=rdata;
    check(rresp==0&&rid==arid&&rlast,"committed read metadata");
    wr(B+'h14,4);
    repeat(6)begin @(posedge clk);check(rvalid&&rdata===previous&&rresp==0&&rid==arid&&rlast,"committed read stable across abort/backpressure");end
    @(negedge clk);rready=1;@(posedge clk);@(negedge clk);rready=0;
    rd(B+'h10000,v,2);check(v==0,"subsequent read after abort is isolated");
    $display("CASE_PASS backpressure_then_read_isolation");

    resetn=0;repeat(8)@(posedge clk);@(negedge clk);resetn=1;
    poll(0,1);rd(B+8,v);check(!v[1]&&!v[5]&&!v[8],"external reset also leaves observation disabled");
    arm();full_capture();abort_hidden();
    serial_half=1.786;repeat(600)@(posedge clk);rd(B+'h18,v);
    check(v>=68&&v<=72,"70MHz independently distinguished from35MHz with4-cycle quantization");
    $display("CASE_PASS reset_recovery_and_70mhz");
    // Synthetic error+invalid observation words must also be stored unchanged.
    // This verifies the diagnostic RAM contract, not actual bad CSI packets.
    @(negedge byteclk);raw_word=32'h04400000;
    arm();full_capture();
    check(first[26] && first[22] && !first[27] && !first[23],
          "diagnostic preserves both error bits with valid=0 instead of filtering observations");
    snapshot("synthetic error/invalid raw observation preserved");abort_hidden();
    $display("CASE_PASS error_observation_preserved");
    // Actual ISERDESE2 + IDELAY + canonical pipeline, both lane identities.
    // Complementary constants have an unambiguous edge/byte value; this does
    // NOT claim arbitrary bit alignment, SoT acquisition or analog eye margin.
    wr(B+'h24,1);poll(8,1);
    @(negedge clk);force dut.sampler_hold=1'b1;
    wait(byte_reset);reset_asserted=$realtime;
    @(negedge clk);release dut.sampler_hold;
    wait(!byte_reset);
    check($realtime-reset_asserted>=16.0*serial_half,"one-control-cycle source pulse stretched past two complete CLKDIV periods");
    poll(8,1);abort_hidden();
    use_real_samples=1;
    for(i=0;i<2;i=i+1) begin
      lane_bit=(i==0);arm();poll(5,1);
      for(integer k=0;k<32;k=k+1)begin
        rd(B+'h10000+4*k,v);
        $display("OBS_CAPTURE case=%0d index=%0d RAM=%08h live=%08h",i,k,v,actual_raw_word);
        // Initial00FF search window contains1F at offset3: 1F xor1D=02,
        // exactly one bit. The existing receiver legitimately latches soft.
        // This expected metadata documents that rule, not receiver admission.
        check(v== (i==0 ? 32'h00a000ff : 32'h0a00ff00),"fresh raw capture faithfully preserves constant data and soft/valid metadata");
      end
      check(default_raw===serial_raw[7:0],"default internal reset mode retains settled raw behavior");
      snapshot($sformatf("known soft boundary case=%0d",i));
      check(serial_hard===3'b000 && serial_error===3'b000 &&
            serial_soft===(i==0 ? 3'b101 : 3'b010) && serial_valid===serial_soft,
            "00-to-FF boundary obeys the existing one-bit soft-match contract");
      abort_hidden();byte_enable=0;
      repeat(30)@(posedge clk);wr(B+'h24,1);repeat(30)@(posedge clk);
      check(byte_reset && !dut.byte_released,"common reset cannot release with stopped byte clock");
      byte_enable=1;
    end
    $display("CASE_PASS shared_reset_warmup_and_real_serdes");
    $display("DPHY_OBSERVER_REVISION4_PASS checks=%0d",checks);$finish;
  end
  initial begin #2000000;snapshot("global simulation timeout");$fatal(1,"global simulation timeout");end
endmodule
