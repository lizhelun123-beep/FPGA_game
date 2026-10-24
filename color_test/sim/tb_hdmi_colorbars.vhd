library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library std;
use std.env.all;

entity tb_hdmi_colorbars is end entity;
architecture test of tb_hdmi_colorbars is
  signal clk : std_logic := '0';
  signal reset : std_logic := '1';
  signal rgb : std_logic_vector(23 downto 0);
  signal hs, vs, de : std_logic;
  signal guard_clk : std_logic := '0';
  signal hold, locked : std_logic := '0';
  signal mmcm_reset : std_logic;
  signal guard_done : boolean := false;
  type colors_t is array(0 to 7) of std_logic_vector(23 downto 0);
  constant colors : colors_t := (x"FFFFFF",x"FFFF00",x"00FFFF",x"00FF00",x"FF00FF",x"FF0000",x"0000FF",x"000000");
begin
  clk <= not clk after 6097561 fs;
  guard_clk <= not guard_clk after 10 ns;
  dut : entity work.hdmi_colorbars_timing
    port map (clk,reset,rgb,hs,vs,de);
  supervisor : entity work.hdmi_colorbars_guard
    port map (guard_clk,hold,locked,mmcm_reset);
  guard_check : process
  begin
    wait for 1 ns;
    assert mmcm_reset='1' report "Power-on reset missing" severity failure;
    wait for 1 us;
    assert mmcm_reset='0' report "Initial hold did not end" severity failure;
    locked <= '1'; wait for 200 ns;
    locked <= '0'; wait for 100 ns;
    assert mmcm_reset='1' report "LOCKED-loss reset missing" severity failure;
    wait for 800 ns;
    assert mmcm_reset='0' report "LOCKED-loss hold did not end" severity failure;
    locked <= '1'; wait for 200 ns;
    hold <= '1'; wait for 1 ps;
    assert mmcm_reset='1' report "Upstream loss did not assert immediately" severity failure;
    hold <= '0'; wait for 30 ns;
    assert mmcm_reset='1' report "Unsafe early reset release" severity failure;
    wait for 1 us;
    assert mmcm_reset='0' report "Upstream recovery failed" severity failure;
    guard_done <= true;
    wait;
  end process;
  raster_check : process
    variable want : std_logic_vector(23 downto 0);
    variable hp, vp, active : std_logic;
    variable active_count : natural := 0;
  begin
    wait until falling_edge(clk); wait until falling_edge(clk);
    reset <= '0';
    for frame in 0 to 1 loop
      active_count := 0;
      for row in 0 to 829 loop
        for col in 0 to 1649 loop
          wait until rising_edge(clk); wait for 1 ps;
          hp:='0'; vp:='0'; active:='0'; want:=x"000000";
          if col >=1390 and col<1430 then hp:='1'; end if;
          if row >=805 and row<810 then vp:='1'; end if;
          if row<800 and col<1280 then
            active:='1'; active_count:=active_count+1;
            want:=colors(col/160);
            if row=0 or row=799 or col=0 or col=1279 then want:=x"FFFFFF"; end if;
            if col>=9 and col<=24 and row>=9 and row<=24 then want:=x"FF0000"; end if;
            if col>=1255 and col<=1270 and row>=9 and row<=24 then want:=x"00FF00"; end if;
            if col>=9 and col<=24 and row>=775 and row<=790 then want:=x"0000FF"; end if;
            if col>=1255 and col<=1270 and row>=775 and row<=790 then want:=x"FFFF00"; end if;
          end if;
          assert hs=hp and vs=vp and de=active and rgb=want
            report "Raster mismatch frame/row/col=" & integer'image(frame) & "/" & integer'image(row) & "/" & integer'image(col) severity failure;
        end loop;
      end loop;
      assert active_count=1024000 report "Wrong active pixel count" severity failure;
    end loop;
    -- Reset during an active line, then verify first pixel restarts coherently.
    for i in 1 to 200 loop wait until rising_edge(clk); end loop;
    wait until falling_edge(clk); reset<='1';
    wait until rising_edge(clk); wait for 1 ps;
    assert rgb=x"000000" and de='0' and hs='0' and vs='0' severity failure;
    wait until falling_edge(clk); reset<='0';
    wait until rising_edge(clk); wait for 1 ps;
    assert rgb=x"FFFFFF" and de='1' and hs='0' and vs='0' severity failure;
    assert guard_done report "Supervisor test incomplete" severity failure;
    report "HDMI_RASTER_GUARD_PASS pixels=2739000 active_per_frame=1024000 frames=2 reset_recovery=PASS" severity note;
    stop;
    wait;
  end process;
end architecture;
