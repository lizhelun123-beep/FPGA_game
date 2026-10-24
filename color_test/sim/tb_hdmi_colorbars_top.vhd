library ieee;
use ieee.std_logic_1164.all;
library std;
use std.env.all;
entity tb_hdmi_colorbars_top is end entity;
architecture test of tb_hdmi_colorbars_top is
  signal ref_clk : std_logic := '0';
  signal cp,cn : std_logic;
  signal dp,dn : std_logic_vector(2 downto 0);
begin
  ref_clk <= not ref_clk after 10 ns;
  dut : entity work.hdmi_colorbars_top port map(ref_clk,cp,cn,dp,dn);
  check : process
    variable previous_edge : time;
  begin
    wait for 100 us;
    assert cp='0' or cp='1' report "No TMDS clock after bounded startup" severity failure;
    wait until rising_edge(cp); previous_edge:=now;
    for i in 1 to 100 loop
      wait until rising_edge(cp);
      assert abs((now-previous_edge)-12195122 fs)<10 ps report "Wrong 82MHz forwarded clock" severity failure;
      previous_edge:=now;
      assert cp=not cn and dp=not dn report "Differential outputs invalid" severity failure;
    end loop;
    report "HDMI_UNISIM_STARTUP_PASS forwarded_clock=82MHz samples=100" severity note;
    stop; wait;
  end process;
  deadline : process begin wait for 200 us; assert false report "Startup deadline" severity failure; wait; end process;
end architecture;
