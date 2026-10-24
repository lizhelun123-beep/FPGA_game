-- Exercise the canonical deserializers; the runner drives asynchronous
-- settled/reset inputs and checks their internal release chains in XSim.
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity tb_dphy_settled is
end tb_dphy_settled;

architecture test of tb_dphy_settled is
   signal ser_clk, div_clk, ctl_clk : std_logic := '0';
   signal settled : std_logic_vector(1 downto 0) := "00";
   signal rst : std_logic := '1';
begin
   ser_clk <= not ser_clk after 1.7855 ns;
   ctl_clk <= not ctl_clk after 2.5 ns;

   lanes: for i in 0 to 1 generate
      dut: entity work.HS_Deserializer
         generic map (kNoLP => false)
         port map (
            dLP0_in => (others => '0'), dLP1_in => (others => '0'),
            dLP0_out => open, dLP1_out => open,
            SerClk => ser_clk, DivClk => div_clk,
            aHSIn => '0', aLPIn => "00", aLPOut => open,
            dDataOut8 => open, dDataOut9 => open, dValid => open,
            dSyncHard => open, dSyncSoft => open, dSyncErr => open,
            CtlClk => ctl_clk, cIDLY_LD => '0', cIDLY_CE => '0',
            cIDLY_INC => '0', cIDLY_CNT => open,
            aRst => rst, aSettled => settled(i));
   end generate;
end test;
