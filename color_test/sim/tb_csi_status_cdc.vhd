library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
library csi;

entity tb_csi_status_cdc is end;
architecture test of tb_csi_status_cdc is
  signal bc, ac : std_logic := '0';
  signal byte_run, resetn : std_logic := '0';
  signal raw_packets : unsigned(31 downto 0) := (others => '0');
  signal raw_crc, packets, crc, serial : std_logic_vector(31 downto 0);
  signal request, busy, en, rst : std_logic;
  signal awaddr, araddr : std_logic_vector(4 downto 0) := (others => '0');
  signal awvalid, awready, wvalid, wready, bvalid, arvalid, arready, rvalid : std_logic := '0';
  signal wdata, rdata : std_logic_vector(31 downto 0) := (others => '0');
  signal wstrb : std_logic_vector(3 downto 0) := (others => '1');
  signal bresp, rresp : std_logic_vector(1 downto 0);
  signal completed : natural := 0;
begin
  ac <= not ac after 5 ns;
  process
  begin
    -- Status counters run on video_aclk (142.857 MHz), independently of AXI.
    wait for 3500 ps;
    if byte_run = '1' then bc <= not bc;
    else bc <= '0'; end if;
  end process;
  process(bc)
  begin
    if rising_edge(bc) then raw_packets <= raw_packets + 1; end if;
  end process;
  raw_crc <= std_logic_vector(raw_packets xor unsigned'(x"A5A55A5A"));
  bridge : entity csi.CSIStatusBridge
    port map (SourceClk => bc, SourcePackets => std_logic_vector(raw_packets),
      SourceCrc => raw_crc, DestClk => ac, DestResetn => resetn, Request => request,
      Busy => busy, Packets => packets, Crc => crc, SnapshotSequence => serial);
  registers : entity csi.MIPI_CSI_2_RX_S_AXI_LITE
    generic map (kVersionMajor => 1, kVersionMinor => 2, C_S_AXI_ADDR_WIDTH => 5)
    port map (xEnable => en, xRst => rst, FrameCount => packets, CrcErrorCount => crc,
      StatusSequence => serial, StatusRequest => request, StatusBusy => busy, FifoOverflow => '0',
      S_AXI_ACLK => ac, S_AXI_ARESETN => resetn,
      S_AXI_AWADDR => awaddr, S_AXI_AWPROT => "000", S_AXI_AWVALID => awvalid, S_AXI_AWREADY => awready,
      S_AXI_WDATA => wdata, S_AXI_WSTRB => wstrb, S_AXI_WVALID => wvalid, S_AXI_WREADY => wready,
      S_AXI_BRESP => bresp, S_AXI_BVALID => bvalid, S_AXI_BREADY => '1',
      S_AXI_ARADDR => araddr, S_AXI_ARPROT => "000", S_AXI_ARVALID => arvalid, S_AXI_ARREADY => arready,
      S_AXI_RDATA => rdata, S_AXI_RRESP => rresp, S_AXI_RVALID => rvalid, S_AXI_RREADY => '1');

  process
    procedure wr(address : natural; value : natural; strobes : std_logic_vector(3 downto 0) := "1111") is
      variable found : boolean := false;
    begin
      wait until falling_edge(ac);
      awaddr <= std_logic_vector(to_unsigned(address,5)); wdata <= std_logic_vector(to_unsigned(value,32));
      wstrb <= strobes; awvalid <= '1'; wvalid <= '1';
      for i in 1 to 32 loop
        wait until rising_edge(ac);
        if awready = '1' and wready = '1' then found := true; exit; end if;
      end loop;
      assert found report "AXI write handshake timeout" severity failure;
      wait until falling_edge(ac); awvalid <= '0'; wvalid <= '0';
      found := false;
      for i in 1 to 32 loop
        wait until rising_edge(ac);
        if bvalid = '1' then
          assert bresp = "00" report "AXI write error" severity failure;
          found := true; exit;
        end if;
      end loop;
      assert found report "AXI write response timeout" severity failure;
    end procedure;
    procedure rd(address : natural; variable value : out std_logic_vector(31 downto 0)) is
      variable found : boolean := false;
    begin
      wait until falling_edge(ac);
      araddr <= std_logic_vector(to_unsigned(address,5)); arvalid <= '1';
      for i in 1 to 32 loop
        wait until rising_edge(ac);
        if arready = '1' then found := true; exit; end if;
      end loop;
      assert found report "AXI read handshake timeout" severity failure;
      wait until falling_edge(ac); arvalid <= '0'; found := false;
      for i in 1 to 32 loop
        wait until rising_edge(ac);
        if rvalid = '1' then
          assert rresp = "00" report "AXI read error" severity failure;
          value := rdata; found := true; exit;
        end if;
      end loop;
      assert found report "AXI read response timeout" severity failure;
    end procedure;
    procedure idle is
      variable flags : std_logic_vector(31 downto 0);
      variable done : boolean := false;
    begin
      for i in 1 to 160 loop
        rd(20,flags);
        if flags(0) = '0' then done := true; exit; end if;
      end loop;
      assert done report "Snapshot busy did not drain" severity failure;
    end procedure;
    procedure finish_snapshot(previous : std_logic_vector(31 downto 0); minimum : unsigned(31 downto 0)) is
      variable value, p, c, frozen : std_logic_vector(31 downto 0);
      variable found : boolean := false;
    begin
      for i in 1 to 160 loop
        rd(16,value);
        if value /= previous then found := true; exit; end if;
      end loop;
      assert found report "Fresh snapshot completion timeout" severity failure;
      rd(4,p); rd(8,c);
      assert unsigned(p) > minimum report "Snapshot predates request/source progress" severity failure;
      assert (unsigned(p) xor unsigned(c)) = unsigned'(x"A5A55A5A") report "Torn counter pair" severity failure;
      frozen := p;
      for i in 1 to 4 loop
        rd(4,p); assert p = frozen report "Status changed without a request" severity failure;
      end loop;
      completed <= completed + 1;
    end procedure;
    variable value, previous : std_logic_vector(31 downto 0);
    variable minimum : unsigned(31 downto 0);
  begin
    byte_run <= '1'; wait for 200 ns;
    wait until falling_edge(ac); resetn <= '1';
    rd(12,value); assert value = x"00010002" report "Version register alias" severity failure;
    rd(16,previous); assert previous = x"00000000" severity failure;
    wr(16,1,"0000"); wait for 1 us;
    rd(16,value); assert value = previous report "Ignored write strobes created request" severity failure;
    for sample in 1 to 12 loop
      idle; rd(16,previous); minimum := raw_packets;
      wr(16,1); finish_snapshot(previous,minimum);
    end loop;
    wait until falling_edge(bc); byte_run <= '0'; wait for 100 ns;
    rd(16,previous); minimum := raw_packets; wr(16,1);
    wait for 2 us;
    rd(16,value); assert value = previous report "Stopped source published old status" severity failure;
    rd(20,value); assert value(0) = '1' report "Stopped source not pending" severity failure;
    byte_run <= '1'; finish_snapshot(previous,minimum);
    for offset in 0 to 5 loop
      idle; wr(16,1); wait for offset * 200 ns;
      wait until falling_edge(ac); resetn <= '0'; wait for 40 ns;
      wait until falling_edge(ac); resetn <= '1';
      idle; rd(16,value);
      assert value = x"00000000" report "Reset-cancelled request published status" severity failure;
      minimum := raw_packets; wr(16,1); finish_snapshot(value,minimum);
    end loop;
    wait for 20 ns;
    assert completed = 19 report "Coverage count mismatch" severity failure;
    report "PASS CSI_STATUS_CDC snapshots=19 reset_offsets=6 stopped_source=1 atomic_pair=1 AXI_registers=1" severity note;
    finish;
  end process;
  process
  begin
    wait for 200 us; assert false report "Status fixture deadline" severity failure;
  end process;
end architecture;
