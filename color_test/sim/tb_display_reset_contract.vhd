library ieee;
use ieee.std_logic_1164.all;
library proc_sys_reset_v5_0_13;
library unisim;
use unisim.vcomponents.all;

entity tb_display_reset_contract is end;
architecture test of tb_display_reset_contract is
  signal refclk, axisclk, pixelclk, serialclk : std_logic := '0';
  signal resetn, locked, enabled, done, ready : std_logic := '0';
  signal pixel_run : boolean := true;
  signal serial_half : time := 1 ns;
  signal pixel_clear : std_logic;
  signal ar, pr : std_logic_vector(0 to 0);
  signal an, pn : std_logic_vector(0 to 0);
begin
  refclk <= not refclk after 5 ns;
  axisclk <= not axisclk after 3.5 ns;
  process begin
    wait for serial_half;
    if pixel_run then serialclk <= not serialclk; else serialclk <= '0'; end if;
  end process;
  guard: entity work.display_clock_guard
    port map(refclk, resetn, locked, enabled, done, ready, open);
  pixel_clear <= not locked;
  pixel_divider: BUFR generic map(BUFR_DIVIDE=>"5", SIM_DEVICE=>"7SERIES")
    port map(O=>pixelclk, CE=>'1', CLR=>pixel_clear, I=>serialclk);
  axis_reset: entity proc_sys_reset_v5_0_13.proc_sys_reset
    generic map(C_EXT_RESET_HIGH=>'0', C_AUX_RESET_HIGH=>'0', C_AUX_RST_WIDTH=>16)
    port map(slowest_sync_clk=>axisclk, ext_reset_in=>resetn, aux_reset_in=>ready,
      mb_debug_sys_rst=>'0', dcm_locked=>'1', mb_reset=>open,
      bus_struct_reset=>open, peripheral_reset=>ar,
      interconnect_aresetn=>open, peripheral_aresetn=>an);
  pixel_reset: entity proc_sys_reset_v5_0_13.proc_sys_reset
    generic map(C_EXT_RESET_HIGH=>'0', C_AUX_RESET_HIGH=>'0', C_AUX_RST_WIDTH=>16)
    port map(slowest_sync_clk=>pixelclk, ext_reset_in=>resetn, aux_reset_in=>ready,
      mb_debug_sys_rst=>'0', dcm_locked=>'1', mb_reset=>open,
      bus_struct_reset=>open, peripheral_reset=>pr,
      interconnect_aresetn=>open, peripheral_aresetn=>pn);
  process(pixelclk)
    variable held : natural := 0;
    variable previous : std_logic := '1';
  begin
    if rising_edge(pixelclk) then
      if pr(0)='1' then held := held+1;
      elsif previous='1' then
        assert held>=32 report "VTC/video pixel reset shorter than 32 pixel edges" severity failure;
        held := 0;
      end if;
      previous := pr(0);
    end if;
  end process;
  process(axisclk)
    variable held : natural := 0;
    variable previous : std_logic := '1';
  begin
    if rising_edge(axisclk) then
      if ar(0)='1' then held := held+1;
      elsif previous='1' then
        assert held>=2 report "AXIS reset shorter than two local edges" severity failure;
        held := 0;
      end if;
      previous := ar(0);
    end if;
  end process;
  process
    procedure isolated is begin
      assert an(0)='0' and pn(0)='0' and ar(0)='1' and pr(0)='1'
        report "domain reset isolation missing" severity failure;
    end;
    procedure released is begin
      assert an(0)='1' and pn(0)='1' and ar(0)='0' and pr(0)='0'
        report "domain reset failed to release" severity failure;
    end;
  begin
    wait for 1 us; isolated;
    resetn <= '1'; locked <= '1'; wait for 2 us; isolated;
    -- Startup clocks are legal but the stream remains reset until DRP completes.
    enabled <= '1'; wait for 100 ns; done <= '1'; wait for 2 us; released;
    enabled <= '0'; done <= '0'; wait for 2 us; isolated;
    -- Runtime clock change with reset held, including an entirely stopped pixel clock.
    locked <= '0'; pixel_run <= false; wait for 500 ns;
    serial_half <= 1346154 fs; pixel_run <= true; locked <= '1';
    wait for 2 us; isolated;
    enabled <= '1'; wait for 100 ns; done <= '1'; wait for 2 us; released;
    -- Unexpected loss: reference/AXIS continue; sticky guard survives clock return.
    locked <= '0'; pixel_run <= false; wait for 2 us;
    assert ready='0' and an(0)='0' report "stopped clock isolation" severity failure;
    locked <= '1'; pixel_run <= true; wait for 3 us; isolated;
    assert ready='0' report "clock-only recovery escaped isolation" severity failure;
    -- Fresh transaction after at least the required reset hold in running domains.
    enabled <= '0'; done <= '0'; wait for 2 us;
    enabled <= '1'; wait for 100 ns; done <= '1'; wait for 2 us; released;
    resetn <= '0'; done <= '1'; wait for 2 us; isolated;
    resetn <= '1'; wait for 2 us; isolated;
    report "PASS display reset contract: exact proc_sys_reset rev13, startup/runtime, held reset, stop/clock-only return, fresh recovery, old done isolation" severity note;
    wait;
  end process;
end architecture;
