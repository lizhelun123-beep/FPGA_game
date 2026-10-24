`timescale 1ns/1ps
// Existing generated VDMA/protocol-converter/reset wrappers, unmodified.
// HP memory is a bounded, ordered AXI3 responder, not a model of PS reset.
module tb_display_ram_contract;
  reg failed=0, finished=0;
  task automatic fail(input string reason);
    failed=1;$fatal(1,"%s",reason);
  endtask
`ifdef RAM_USE_NETLIST
  // Verified unconnected in actual system.v and tied000 in the exported DCP.
  // Never use this pruned output to mask data: all24 data bits are checked.
  localparam [2:0] EXPECTED_KEEP=3'b000;
`else
  localparam [2:0] EXPECTED_KEEP=3'b111;
`endif
  reg ctrl_clk=0, mem_clk=0, mem_run=1, ps_resetn=0, hp_reset=1;
  always #5 ctrl_clk=~ctrl_clk;
  always #3.5 if(mem_run) mem_clk=~mem_clk; else mem_clk=0;
  wire [0:0] interconnect_n, peripheral_n, vdma_n;
  system_proc_sys_reset_150M_0 reset_mem(
    .slowest_sync_clk(mem_clk),.ext_reset_in(ps_resetn),.aux_reset_in(1'b1),
    .mb_debug_sys_rst(1'b0),.dcm_locked(1'b1),.mb_reset(),.bus_struct_reset(),
    .peripheral_reset(),.interconnect_aresetn(interconnect_n),.peripheral_aresetn(peripheral_n));
  system_rst_100M_0 reset_ctrl(
    .slowest_sync_clk(ctrl_clk),.ext_reset_in(ps_resetn),.aux_reset_in(1'b1),
    .mb_debug_sys_rst(1'b0),.dcm_locked(1'b1),.mb_reset(),.bus_struct_reset(),
    .peripheral_reset(),.interconnect_aresetn(),.peripheral_aresetn(vdma_n));

  reg awvalid=0,wvalid=0,bready=1,arvalid=0,rready=1;
  reg [8:0] awaddr=0,araddr=0;
  reg [31:0] wdata=0;
  wire awready,wready,bvalid,arready,rvalid;
  wire [1:0] bresp,rresp;
  wire [31:0] rdata;
  wire [31:0] va;
  wire [7:0] vl;
  wire [2:0] vs,vp;
  wire [1:0] vb,vrresp;
  wire [3:0] vc;
  wire vav,v_arready,vrl,vrv,vrr;
  wire [63:0] vrd;
  wire [23:0] td;
  wire [2:0] tk;
  wire [0:0] tu;
  wire tv,tl;
  integer stream_cycle=0;
  wire stream_ready=(stream_cycle%31)<24;
  always @(posedge mem_clk) stream_cycle<=stream_cycle+1;
  wire [5:0] frame_pointer;
`ifdef RAM_USE_NETLIST
  ram_vdma_snapshot vdma(
`else
  system_axi_vdma_0_0 vdma(
`endif
    .s_axi_lite_aclk(ctrl_clk),.m_axi_mm2s_aclk(mem_clk),.m_axis_mm2s_aclk(mem_clk),.axi_resetn(vdma_n[0]),
    .s_axi_lite_awvalid(awvalid),.s_axi_lite_awready(awready),.s_axi_lite_awaddr(awaddr),
    .s_axi_lite_wvalid(wvalid),.s_axi_lite_wready(wready),.s_axi_lite_wdata(wdata),
    .s_axi_lite_bresp(bresp),.s_axi_lite_bvalid(bvalid),.s_axi_lite_bready(bready),
    .s_axi_lite_arvalid(arvalid),.s_axi_lite_arready(arready),.s_axi_lite_araddr(araddr),
    .s_axi_lite_rvalid(rvalid),.s_axi_lite_rready(rready),.s_axi_lite_rdata(rdata),.s_axi_lite_rresp(rresp),
    .mm2s_frame_ptr_out(frame_pointer),.m_axi_mm2s_araddr(va),.m_axi_mm2s_arlen(vl),
    .m_axi_mm2s_arsize(vs),.m_axi_mm2s_arburst(vb),.m_axi_mm2s_arprot(vp),.m_axi_mm2s_arcache(vc),
    .m_axi_mm2s_arvalid(vav),.m_axi_mm2s_arready(v_arready),.m_axi_mm2s_rdata(vrd),.m_axi_mm2s_rresp(vrresp),
    .m_axi_mm2s_rlast(vrl),.m_axi_mm2s_rvalid(vrv),.m_axi_mm2s_rready(vrr),
    .m_axis_mm2s_tdata(td),.m_axis_mm2s_tkeep(tk),.m_axis_mm2s_tuser(tu),
    .m_axis_mm2s_tvalid(tv),.m_axis_mm2s_tready(stream_ready),.m_axis_mm2s_tlast(tl),.mm2s_introut());
  wire [31:0] ha;
  wire [3:0] hl;
  wire [2:0] hs;
  wire [1:0] hb;
  wire hav,har,hrv,hrr,hrl;
  wire [63:0] hrd;
`ifdef RAM_USE_NETLIST
  ram_pc_snapshot protocol_converter(
`else
  system_auto_pc_2 protocol_converter(
`endif
    .aclk(mem_clk),.aresetn(peripheral_n[0]),
    .s_axi_araddr(va),.s_axi_arlen(vl),.s_axi_arsize(vs),.s_axi_arburst(vb),
    .s_axi_arlock(1'b0),.s_axi_arcache(vc),.s_axi_arprot(vp),.s_axi_arregion(4'b0),.s_axi_arqos(4'b0),
    .s_axi_arvalid(vav),.s_axi_arready(v_arready),.s_axi_rdata(vrd),.s_axi_rresp(vrresp),
    .s_axi_rlast(vrl),.s_axi_rvalid(vrv),.s_axi_rready(vrr),
    .m_axi_araddr(ha),.m_axi_arlen(hl),.m_axi_arsize(hs),.m_axi_arburst(hb),
    .m_axi_arlock(),.m_axi_arcache(),.m_axi_arprot(),.m_axi_arqos(),
    .m_axi_arvalid(hav),.m_axi_arready(har),.m_axi_rdata(hrd),.m_axi_rresp(2'b0),
    .m_axi_rlast(hrl),.m_axi_rvalid(hrv),.m_axi_rready(hrr));

  reg hp_active=0, hold_response=0;
  integer response_delay=0, beats_left=0, hp_transactions=0, hp_beats=0;
  reg [31:0] hp_address=0;
  function automatic [7:0] byte_at(input [31:0] a);
    byte_at=a[7:0]^a[15:8]^a[31:24];
  endfunction
  function automatic [63:0] word_at(input [31:0] a);
    integer k;
    for(k=0;k<8;k=k+1) word_at[k*8+:8]=byte_at(a+k);
  endfunction
  assign har=!hp_active && !hp_reset;
  assign hrv=hp_active && response_delay==0 && !hp_reset;
  assign hrl=beats_left==1;
  assign hrd=word_at(hp_address);
  always @(posedge mem_clk) begin
    if(hp_reset) begin hp_active<=0;response_delay<=0;beats_left<=0;end
    else if(hav && har) begin
      if(hs!==3 || hb!==1) fail("Unsupported memory request size/burst");
      hp_active<=1;hp_address<=ha;beats_left<=hl+1;response_delay<=8;hp_transactions<=hp_transactions+1;
    end else if(hp_active) begin
      if(response_delay>0) begin if(!hold_response) response_delay<=response_delay-1;end
      else if(hrv && hrr) begin
        hp_beats<=hp_beats+1;
        if(beats_left==1) hp_active<=0;
        else begin beats_left<=beats_left-1;hp_address<=hp_address+8;end
      end
    end
  end
  // Check the actual stream, including every byte/SOF/EOL/TKEEP, not a prefix.
  reg checking=0;
  reg [31:0] expected_base=0;
  integer index=0, complete_frames=0, case_id=0, accepted_pixels=0;
  reg [31:0] expected_address;
  reg [23:0] expected_data;
  always @(posedge mem_clk) if(checking && tv===1'b1 && stream_ready) begin
    expected_address=expected_base+(index/1280)*5760+(index%1280)*3;
    expected_data={byte_at(expected_address+2),byte_at(expected_address+1),byte_at(expected_address)};
    if(td!==expected_data || tk!==EXPECTED_KEEP || tu[0]!==(index==0) || tl!==((index%1280)==1279)) begin
      $display("RAM_FAIL case=%0d index=%0d td=%h expected=%h keep=%b SOF=%b EOL=%b vreset=%b pcreset=%b hp_active=%b hpaddr=%h left=%0d",case_id,index,td,expected_data,tk,tu,tl,vdma_n,peripheral_n,hp_active,hp_address,beats_left);
      fail("Full-frame/data-generation contract failed");
    end
    accepted_pixels=accepted_pixels+1;
    if((index+1)%(1280*64)==0)
      $display("RAM_PROGRESS case=%0d line=%0d frames=%0d",case_id,(index+1)/1280,complete_frames);
    if(index==1280*720-1) begin index=0;complete_frames=complete_frames+1;
      $display("RAM_FRAME_PASS case=%0d frames=%0d pixels=%0d hp_beats=%0d",case_id,complete_frames,accepted_pixels,hp_beats);
    end else index=index+1;
  end
  task automatic write_reg(input [8:0] a,input [31:0] d);
    @(negedge ctrl_clk);awaddr=a;wdata=d;awvalid=1;wvalid=1;
    fork
      begin do @(posedge ctrl_clk); while(awready!==1'b1); @(negedge ctrl_clk);awvalid=0;end
      begin do @(posedge ctrl_clk); while(wready!==1'b1); @(negedge ctrl_clk);wvalid=0;end
    join
    do @(posedge ctrl_clk);while(bvalid!==1'b1);
    if(bresp!==0) fail("AXIL write response");
    @(negedge ctrl_clk);
  endtask
  task automatic read_reg(input [8:0] a,output [31:0] d);
    @(negedge ctrl_clk);araddr=a;arvalid=1;
    do @(posedge ctrl_clk);while(arready!==1'b1);
    @(negedge ctrl_clk);arvalid=0;
    do @(posedge ctrl_clk);while(rvalid!==1'b1);
    if(rresp!==0) fail("AXIL read response");
    d=rdata;@(negedge ctrl_clk);
  endtask
  task automatic wait_halted;
    reg [31:0] s;integer n;
    begin s=0;n=0;while(!s[0] && n<50000) begin read_reg(9'h004,s);n=n+1;end
      if(!s[0] || (s&32'hff0)!=0) fail($sformatf("HALTED/error contract status=%h",s));
      if(hp_active || hav) fail($sformatf("HALTED before HP/command drain active=%b ARVALID=%b",hp_active,hav));
      $display("RAM_HALT_PASS case=%0d polls=%0d hp_active=%b",case_id,n,hp_active);
    end
  endtask
  task automatic start_image(input [31:0] base);
    begin
      checking=0;write_reg(9'h000,1);write_reg(9'h028,0);
      write_reg(9'h05c,base);write_reg(9'h060,base);write_reg(9'h064,base);
      write_reg(9'h058,5760);write_reg(9'h054,3840);
      @(negedge mem_clk);expected_base=base;index=0;checking=1;
      write_reg(9'h050,720);
    end
  endtask
  task automatic one_frame;
    integer old_frames;
    begin old_frames=complete_frames;wait(complete_frames>old_frames);end
  endtask
  task automatic evidence_window;
`ifdef RAM_FIFO_EPOCH_MODE
    integer first_pixel;
    begin
      first_pixel=accepted_pixels;
      // Warned RAMs:1024 rows,64payload bits/row.24576payload bytes span
      // three complete write-address wraps. Geometry remains1280x720/stride5760.
      wait(accepted_pixels>=first_pixel+8192);@(negedge mem_clk);
      $display("RAM_FIFO_EPOCH_PASS case=%0d pixels=8192 bytes=24576 complete_frames=%0d",case_id,complete_frames);
    end
`else
    begin one_frame();end
`endif
  endtask
  task automatic stable_resets;
    begin wait(vdma_n[0]===1 && peripheral_n[0]===1 && interconnect_n[0]===1);
      repeat(64) @(posedge mem_clk);end
  endtask
  reg [31:0] status,control;
  initial begin
    $display("RAM_BEGIN exact VDMA6.3rev16/PC2.1rev28/PSR5.0rev13,720p/stride5760");
    #500;hp_reset=0;ps_resetn=1;stable_resets();
    case_id=0;start_image(32'h01000000);evidence_window();
    // A queued HP response is deliberately delayed while stop is requested.
    case_id=1;wait(hp_active && response_delay>0);hold_response=1;
    write_reg(9'h000,0);read_reg(9'h004,status);
    if(status[0]) fail("HALTED falsely asserted with an unfinished memory read");
    hold_response=0;wait_halted();checking=0;
    // No reset between stop/restart: matches the current native C path.
    case_id=2;start_image(32'h02000000);evidence_window();
    // Soft reset has to drain PC/HP before its local FIFO reset completes.
    case_id=3;checking=0;wait(hrv && hrr && hrl);write_reg(9'h000,4);
    control=4;repeat(20000) begin
      if(control[2]) read_reg(9'h000,control);
    end
    if(control[2]) fail("Soft reset did not finish");
    wait_halted();start_image(32'h03000000);evidence_window();
    // Supported recovery probe: reset asserted while FCLK1 is stopped, kept
    // asserted after the clock is stable. The HP responder is reset too.
    case_id=4;checking=0;ps_resetn=0;hp_reset=1;
    #2;mem_run=0;#500;mem_run=1;repeat(64) @(posedge mem_clk);
    ps_resetn=1;hp_reset=0;stable_resets();start_image(32'h04000000);evidence_window();
    write_reg(9'h000,0);wait_halted();checking=0;
`ifdef RAM_FIFO_EPOCH_MODE
    $display("RAM_SUPPORTED_FIFO_CASES_PASS complete_frames=%0d pixels=%0d",complete_frames,accepted_pixels);
`else
    $display("RAM_SUPPORTED_CASES_PASS frames=%0d pixels=%0d",complete_frames,accepted_pixels);
`endif
    // Separate negative boundary: PL reset does NOT imply PS/HP cancellation.
    // Retain an old ordered response until a new read is offered. Do not turn
    // this into an expected-success waiver or silently reset the HP model.
    case_id=5;start_image(32'h05000000);
    wait(hp_active && response_delay>0);hold_response=1;checking=0;
    $display("RAM_PL_ONLY_RESET_BOUNDARY old_address=%h pending=%b",hp_address,hp_active);
    ps_resetn=0;#500;ps_resetn=1;stable_resets();
    start_image(32'h06000000);
    wait(hav);hold_response=0;
    evidence_window();write_reg(9'h000,0);wait_halted();checking=0;
`ifdef RAM_FIFO_EPOCH_MODE
    $display("RAM_ALL_FIFO_CASES_PASS complete_frames=%0d",complete_frames);
`else
    $display("RAM_ALL_CASES_PASS frames=%0d",complete_frames);
`endif
    finished=1;$finish;
  end
  initial begin #60000000;
    $display("RAM_TIMEOUT case=%0d checking=%b index=%0d vreset=%b pcreset=%b hpactive=%b addr=%h remain=%0d AR=%b/%b R=%b/%b VDMA_R=%b/%b",case_id,checking,index,vdma_n,peripheral_n,hp_active,hp_address,beats_left,hav,har,hrv,hrr,vrv,vrr);
    fail("RAM contract timeout");
  end
  initial begin
    wait(case_id==5 && checking);#100000;
    if(index==0) begin
      $display("RAM_PENDING_RESPONSE_BLOCK case=5 hp_active=%b address=%h AR=%b/%b HP_R=%b/%b VDMA_R=%b/%b",hp_active,hp_address,hav,har,hrv,hrr,vrv,vrr);
      fail("PL-only reset cannot cancel an old HP response");
    end
  end
endmodule
