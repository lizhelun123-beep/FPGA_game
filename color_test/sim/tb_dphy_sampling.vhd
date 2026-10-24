-- Functional only: actual canonical top, UNISIM primitives, two independent LP
-- lanes. Serial stimulus and PPI observations are exported separately; the
-- runner reconstructs its oracle from the transmitted bits, not DUT internals.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use ieee.std_logic_textio.all;

entity tb_dphy_sampling is
   generic (kControllerTest : boolean := false);
end;
architecture test of tb_dphy_sampling is
   constant UI : time := 1785500 fs;
   signal refclk : std_logic := '0';
   signal txclk : std_logic := '0';
   signal clock_run : std_logic := '1';
   signal rst : std_logic := '1';
   signal clock_lp : std_logic_vector(1 downto 0) := "11";
   signal lp0, lp1 : std_logic_vector(1 downto 0) := "11";
   signal serial_data : std_logic_vector(1 downto 0) := "00";
   signal scenario : integer := -1;
   signal audit_tick : std_logic := '0';
   type bytes_t is array(0 to 1) of std_logic_vector(7 downto 0);
   type configs_t is array(0 to 1) of bytes_t;
   type bits_t is array(0 to 1) of std_logic_vector(1 downto 0);
   signal data : configs_t;
   signal valid, active, sync, soterr, softerr : bits_t;
   signal byteclk, ready, ddrclk : std_logic_vector(0 to 1);
   function prefix return string is
   begin
      if kControllerTest then return "control"; else return "primitive"; end if;
   end;
   file stimulus : text open write_mode is prefix & "_stimulus.txt";
   file trace : text open write_mode is prefix & "_trace.txt";

   procedure event_line(constant kind : string; constant n : integer;
                        constant bits : std_logic_vector) is
      variable l : line;
   begin
      write(l, now, unit => fs); write(l, string'(" "));
      write(l, kind); write(l, string'(" ")); write(l, n);
      write(l, string'(" ")); write(l, bits); writeline(stimulus, l);
   end;
begin
   refclk <= not refclk after 2.5 ns;
   process
   begin
      wait for UI;
      if clock_run = '1' then txclk <= not txclk;
      else txclk <= '0'; end if;
   end process;

   configs: for c in 0 to 1 generate
      dut: entity work.MIPI_DPHY_Receiver
         generic map (kNoOfDataLanes => 2, kDebug => false,
            kGenerateAXIL => false, kLPFromLane0 => false,
            kPPISharedEnable => true, kBUFH_DDIRECT_M3 => c = 1)
         port map (
            dphy_clk_hs_p => txclk, dphy_clk_hs_n => not txclk,
            dphy_clk_lp_p => clock_lp(1), dphy_clk_lp_n => clock_lp(0),
            dphy_data_hs_p => serial_data, dphy_data_hs_n => not serial_data,
            dphy_data_lp_p(0) => lp0(1), dphy_data_lp_p(1) => lp1(1),
            dphy_data_lp_n(0) => lp0(0), dphy_data_lp_n(1) => lp1(0),
            RefClk => refclk, aRst => rst,
            RxDDRClkHS => ddrclk(c), RxByteClkHS => byteclk(c),
            aRxClkActiveHS => ready(c), aClkEnable => '1',
            aClkForceRxmode => '0', aD0Enable => '1', aD1Enable => '1',
            aD0ForceRxmode => '0', aD1ForceRxmode => '0',
            rbD0RxDataHS => data(c)(0), rbD1RxDataHS => data(c)(1),
            rbD0RxValidHS => valid(c)(0), rbD1RxValidHS => valid(c)(1),
            rbD0RxActiveHS => active(c)(0), rbD1RxActiveHS => active(c)(1),
            rbD0RxSyncHS => sync(c)(0), rbD1RxSyncHS => sync(c)(1),
            rbD0ErrSotHS => soterr(c)(0), rbD1ErrSotHS => soterr(c)(1),
            rbD0ErrSotSyncHS => softerr(c)(0), rbD1ErrSotSyncHS => softerr(c)(1),
            s_axi_lite_aclk => refclk, s_axi_lite_aresetn => '1',
            s_axi_lite_awaddr => (others => '0'), s_axi_lite_awprot => "000",
            s_axi_lite_awvalid => '0', s_axi_lite_wdata => (others => '0'),
            s_axi_lite_wstrb => (others => '0'), s_axi_lite_wvalid => '0',
            s_axi_lite_bready => '0', s_axi_lite_araddr => (others => '0'),
            s_axi_lite_arprot => "000", s_axi_lite_arvalid => '0', s_axi_lite_rready => '0');
      process
         variable l : line;
      begin
         wait until rising_edge(byteclk(c));
         -- PPI is consumed by downstream flops at the edge, before updates.
         for lane in 0 to 1 loop
            write(l, now, unit => fs); write(l, string'(" "));
            write(l, c); write(l, string'(" ")); write(l, lane);
            write(l, string'(" ")); write(l, scenario);
            write(l, string'(" ")); write(l, ready(c));
            write(l, string'(" ")); write(l, valid(c)(lane));
            write(l, string'(" ")); hwrite(l, data(c)(lane));
            write(l, string'(" ")); write(l, sync(c)(lane));
            write(l, string'(" ")); write(l, active(c)(lane));
            write(l, string'(" ")); write(l, soterr(c)(lane));
            write(l, string'(" ")); write(l, softerr(c)(lane));
            writeline(trace, l);
         end loop;
      end process;
   end generate;

   process
      variable a, b : std_logic_vector(7 downto 0);
      procedure bit_pair(constant v : std_logic_vector(1 downto 0)) is
      begin
         serial_data <= v;
         event_line("BIT", scenario, v);
         wait for UI;
      end;
      procedure byte_pair(constant x, y : std_logic_vector(7 downto 0)) is
      begin
         for i in 0 to 7 loop bit_pair(y(i) & x(i)); end loop;
         audit_tick <= not audit_tick;
      end;
      procedure burst(constant id, offset, rf : integer) is
      begin
         scenario <= id;
         lp0 <= "11"; lp1 <= "11"; serial_data <= "00";
         wait for 300 ns;
         lp0 <= "01"; lp1 <= "01"; wait for 100 ns;
         lp0 <= "00"; lp1 <= "00"; wait for 400 ns;
         -- Anchor to an actual reference raw-word boundary, so all eight
         -- offsets are exercised regardless of the previous burst length.
         -- Its 600 ps clock IDELAY plus 200 ps gives the 800 ps pin launch.
         wait until rising_edge(byteclk(0));
         wait for 200 ps + (offset + rf) * UI;
         event_line("SOT", id, "00");
         byte_pair(x"B8", x"B8");
         event_line("PAYLOAD", id, "00");
         for i in 0 to 31 loop
            a := std_logic_vector(to_unsigned((i*73 + id*17 + 37) mod 256, 8));
            b := std_logic_vector(to_unsigned((i*109 + id*29 + 83) mod 256, 8));
            byte_pair(a,b);
         end loop;
         event_line("TRAIL", id, "00");
         for i in 0 to 11 loop byte_pair(x"FF", x"FF"); end loop;
         lp0 <= "11"; lp1 <= "11";
         event_line("EXIT", id, "11");
         wait for 300 ns;
      end;
   begin
      wait for 1 ps;
      if kControllerTest then wait; end if;
      wait for 300 ns; rst <= '0'; wait for 1 us;
      clock_lp <= "01"; wait for 100 ns; clock_lp <= "00";
      wait for 5 us;
      assert ready = "11" report "Early-burst clock qualification timeout" severity failure;
      -- Clock-ready is not permission to bypass the data-lane 100 us T_INIT.
      burst(98,2,0);
      -- Preserve the real data-lane 100 us initialization timer.
      wait for 110 us;
      assert ready = "11" report "Primitive startup timeout" severity failure;
      for rf in 0 to 1 loop
         for offset in 0 to 7 loop burst(rf*8+offset,offset,rf); end loop;
      end loop;
      scenario <= 16;
      clock_run <= '0'; clock_lp <= "11";
      wait for 500 ns;
      assert ready(1) = '0' report "Candidate ready survived stopped HS clock" severity failure;
      clock_run <= '1'; wait for 300 ns;
      clock_lp <= "01"; wait for 100 ns; clock_lp <= "00";
      wait for 15 us;
      assert ready(1) = '1' report "Candidate did not relock" severity failure;
      burst(17,3,1);
      report "DPHY_PRIMITIVE_STIMULUS_DONE" severity note;
      wait;
   end process;
end;

entity tb_dphy_sampling_control is end;
architecture test of tb_dphy_sampling_control is
begin
   fixture: entity work.tb_dphy_sampling generic map (kControllerTest => true);
end;
