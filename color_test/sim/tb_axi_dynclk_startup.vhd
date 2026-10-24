library ieee;
use ieee.std_logic_1164.all;

entity tb_axi_dynclk_startup is end;
architecture test of tb_axi_dynclk_startup is
  signal clk, resetn, locked, ready, pixel, serial : std_logic := '0';
  signal arvalid, arready, rvalid : std_logic := '0';
  signal rdata : std_logic_vector(31 downto 0);
  signal rresp : std_logic_vector(1 downto 0);
begin
  clk <= not clk after 5 ns;
  dut: entity work.axi_dynclk
    port map(REF_CLK_I=>clk, PXL_CLK_O=>pixel, PXL_CLK_5X_O=>serial,
      LOCKED_O=>locked, DISPLAY_READY_O=>ready,
      s00_axi_aclk=>clk, s00_axi_aresetn=>resetn,
      s00_axi_awaddr=>"00000", s00_axi_awprot=>"000", s00_axi_awvalid=>'0',
      s00_axi_awready=>open, s00_axi_wdata=>(others=>'0'),
      s00_axi_wstrb=>"1111", s00_axi_wvalid=>'0', s00_axi_wready=>open,
      s00_axi_bresp=>open, s00_axi_bvalid=>open, s00_axi_bready=>'1',
      s00_axi_araddr=>"00100", s00_axi_arprot=>"000", s00_axi_arvalid=>arvalid,
      s00_axi_arready=>arready, s00_axi_rdata=>rdata, s00_axi_rresp=>rresp,
      s00_axi_rvalid=>rvalid, s00_axi_rready=>'1');
  process
  begin
    wait for 100 ns; resetn <= '1';
    wait until locked='1' for 10 us;
    assert locked='1' report "real MMCM did not lock at startup" severity failure;
    wait for 200 ns;
    assert ready='0' report "initial SRDY/raw lock falsely qualified display" severity failure;
    wait until falling_edge(clk); arvalid <= '1';
    wait until rising_edge(clk) and arready='1';
    wait until falling_edge(clk); arvalid <= '0';
    wait until rising_edge(clk) and rvalid='1';
    assert rresp="00" and rdata(1 downto 0)="00"
      report "startup STATUS0/READY ABI changed" severity failure;
    report "PASS axi_dynclk real MMCM/DRP/BUFR startup and STATUS ABI" severity note;
    wait;
  end process;
end architecture;
