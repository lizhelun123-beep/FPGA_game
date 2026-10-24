-- One fixed low-rate canonical production PHY; no alternate receiver model.
-- All clocks derive from one integer-femtosecond source; BUFR divides by four.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use ieee.std_logic_textio.all;

entity tb_dphy_rate93 is end;
architecture test of tb_dphy_rate93 is
   constant UI : time := 10_714_286 fs;
   constant NOMINAL_ENTRY : time := 200 ns + 9*UI;
   constant EARLY_STRESS : time := 145 ns + 10*UI;
   signal refclk, txclk : std_logic := '0';
   signal clock_run : std_logic := '0';
   signal rst : std_logic := '1';
   signal axi_resetn : std_logic := '0';
   signal enable : std_logic := '1';
   signal clock_lp : std_logic_vector(1 downto 0) := "11";
   signal lp0, lp1 : std_logic_vector(1 downto 0) := "11";
   signal serial_data : std_logic_vector(1 downto 0) := "00";
   signal scenario : integer := -1;
   signal source_tick : natural := 0;
   signal audit_tick : std_logic := '0';
   signal done : std_logic := '0';
   signal data : std_logic_vector(15 downto 0);
   signal valid, active, sync, soterr, softerr : std_logic_vector(1 downto 0);
   signal byteclk, ready, ddrclk, clock_stop : std_logic;
   file stimulus : text open write_mode is "stimulus.txt";
   file trace : text open write_mode is "trace.txt";
   file clocks : text open write_mode is "clocks.txt";
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
      variable l : line;
   begin
      wait on txclk, byteclk;
      write(l,now,unit=>fs); write(l,string'(" "));
      write(l,txclk); write(l,string'(" ")); write(l,byteclk);
      writeline(clocks,l);
   end process;
   process
   begin
      wait for UI;
      if clock_run = '1' then
         txclk <= not txclk; source_tick <= source_tick+1;
      else txclk <= '0'; end if;
   end process;
   dut: entity work.MIPI_DPHY_Receiver
      generic map (kNoOfDataLanes => 2, kDebug => false,
         kGenerateAXIL => true, kGenerateMMCM => false,
         kLPFromLane0 => false, kPPISharedEnable => true,
         kBUFH_DDIRECT_M3 => false,
         kAddDelayClk_ps => 0, kAddDelayData0_ps => 0, kAddDelayData1_ps => 0)
      port map (
         dphy_clk_hs_p => txclk, dphy_clk_hs_n => not txclk,
         dphy_clk_lp_p => clock_lp(1), dphy_clk_lp_n => clock_lp(0),
         dphy_data_hs_p => serial_data, dphy_data_hs_n => not serial_data,
         dphy_data_lp_p(0) => lp0(1), dphy_data_lp_p(1) => lp1(1),
         dphy_data_lp_n(0) => lp0(0), dphy_data_lp_n(1) => lp1(0),
         RefClk => refclk, aRst => rst,
         RxDDRClkHS => ddrclk, RxByteClkHS => byteclk,
         aRxClkActiveHS => ready, aClkStopstate => clock_stop,
         aClkEnable => enable, aD0Enable => enable, aD1Enable => enable,
         aClkForceRxmode => '0', aD0ForceRxmode => '0', aD1ForceRxmode => '0',
         rbD0RxDataHS => data(7 downto 0), rbD1RxDataHS => data(15 downto 8),
         rbD0RxValidHS => valid(0), rbD1RxValidHS => valid(1),
         rbD0RxActiveHS => active(0), rbD1RxActiveHS => active(1),
         rbD0RxSyncHS => sync(0), rbD1RxSyncHS => sync(1),
         rbD0ErrSotHS => soterr(0), rbD1ErrSotHS => soterr(1),
         rbD0ErrSotSyncHS => softerr(0), rbD1ErrSotSyncHS => softerr(1),
         s_axi_lite_aclk => refclk, s_axi_lite_aresetn => axi_resetn,
         s_axi_lite_awaddr => "0000", s_axi_lite_awprot => "000",
         s_axi_lite_awvalid => '0', s_axi_lite_wdata => (others => '0'),
         s_axi_lite_wstrb => "1111", s_axi_lite_wvalid => '0',
         s_axi_lite_bready => '1', s_axi_lite_araddr => "0000",
         s_axi_lite_arprot => "000", s_axi_lite_arvalid => '0', s_axi_lite_rready => '1');

   -- Observe at the actual downstream sampling edge, before delta-cycle updates.
   process
      variable l : line;
   begin
      wait until rising_edge(byteclk);
      for lane in 0 to 1 loop
         write(l, now, unit => fs); write(l, string'(" "));
         write(l, scenario); write(l, string'(" ")); write(l, lane);
         write(l, string'(" ")); write(l, ready);
         write(l, string'(" ")); write(l, valid(lane));
         write(l, string'(" ")); hwrite(l, data(8*lane+7 downto 8*lane));
         write(l, string'(" ")); write(l, sync(lane));
         write(l, string'(" ")); write(l, active(lane));
         write(l, string'(" ")); write(l, soterr(lane));
         write(l, string'(" ")); write(l, softerr(lane)); writeline(trace,l);
      end loop;
   end process;

   process
      variable a,b : std_logic_vector(7 downto 0);
      procedure bits(constant v : std_logic_vector(1 downto 0)) is
      begin
         serial_data <= v; event_line("BIT",scenario,v); wait for UI;
      end;
      procedure bytes(constant x,y : std_logic_vector(7 downto 0)) is
      begin for i in 0 to 7 loop bits(y(i)&x(i)); end loop; end;
      procedure snapshot(constant label_name : string) is
      begin
         event_line(label_name,scenario,"00"); audit_tick <= not audit_tick;
         wait for 1 ps;
      end;
      procedure clock_entry is
      begin
         clock_lp <= "11"; wait for 300 ns;
         clock_lp <= "01"; wait for 60 ns;
         clock_lp <= "00"; wait for 450 ns;
         clock_run <= '1'; wait for 3 us;
      end;
      procedure reset_with_stopped_clock(constant id : integer) is
      begin
         scenario <= id; wait for 1 ps;
         event_line("RESET_BEGIN",id,"00");
         lp0 <= "11"; lp1 <= "11"; serial_data <= "00";
         clock_lp <= "11"; clock_run <= '0'; rst <= '1';
         wait for 1 us; snapshot("RESET_STOPPED");
         rst <= '0'; wait for 1 us; snapshot("RELEASE_STOPPED");
         clock_entry; wait for 110 us; snapshot("RESET_RECOVERED");
      end;
      procedure burst(constant id,phase : integer; constant entry : time;
                      constant fault : natural := 0) is
      begin
         scenario <= id; wait for 1 ps;
         event_line("BEGIN",id,"00");
         lp0 <= "11"; lp1 <= "11"; serial_data <= "00"; wait for 2 us;
         lp0 <= "01"; lp1 <= "01"; event_line("LP01",id,"01");
         wait for 80 ns;
         -- Source pin phase, never a DUT internal alignment/ready signal.
         wait until source_tick mod 8 = 0;
         wait for phase*UI + 7 ns;
         lp0 <= "00"; lp1 <= "00"; event_line("LP00",id,"00");
         wait for entry;
         event_line("SOT",id,"00"); bytes(x"B8",x"B8");
         event_line("PAYLOAD",id,"00");
         for i in 0 to 31 loop
            a := std_logic_vector(to_unsigned((i*73+id*17+37) mod 256,8));
            b := std_logic_vector(to_unsigned((i*109+id*29+83) mod 256,8));
            bytes(a,b);
            if i=7 and fault/=0 then
               if fault=1 then
                  enable <= '0'; event_line("ABORT",id,"00");
               else
                  clock_run <= '0'; event_line("CLOCK_STOP",id,"00");
               end if;
               wait for 400 ns; snapshot("FAULT_BOUND");
               wait for 600 ns; snapshot("FAULT_HOLD");
               exit;
            end if;
         end loop;
         if fault=0 then
            event_line("TRAIL",id,"00");
            for i in 0 to 11 loop bytes(x"FF",x"FF"); end loop;
         end if;
         if fault/=2 then lp0 <= "11"; lp1 <= "11"; end if;
         event_line("EXIT",id,"11");
         wait for 2 us; snapshot("END");
      end;
      procedure recover_epoch(constant id : integer;
                              constant reinitialize : boolean := false) is
         variable reenabled_at : time;
      begin
         scenario <= id; wait for 1 ps;
         lp0 <= "00"; lp1 <= "00";
         enable <= '1'; clock_run <= '1';
         reenabled_at := now;
         event_line("RESUME_OLD_EPOCH",id,"00");
         wait for 2 us; snapshot("NO_CLOCK_EPOCH");
         clock_entry; snapshot("CLOCK_ONLY_EPOCH");
         -- Keep data LP00 through clock recovery: only a subsequent fresh
         -- data LP11/01/00 entry may release that lane's deserializer.
         lp0 <= "11"; lp1 <= "11"; wait for 400 ns;
         snapshot("DATA_STOP_REOBSERVED");
         if reinitialize then
            -- Disable drives the existing cIntRst/T_INIT path. Qualify its
            -- 100 us plus control synchronizer margin BEFORE the new LP entry;
            -- never extend the SoT guard or wait on an internal DUT condition.
            if now < reenabled_at + 100_100 ns then
               wait for reenabled_at + 100_100 ns - now;
            end if;
            snapshot("INIT_WAIT_COMPLETE");
         end if;
      end;
   begin
      wait for 300 ns; axi_resetn <= '1'; rst <= '0';
      clock_entry; wait for 110 us;
      snapshot("STARTUP");
      burst(0,0,1200 ns);
      -- A short idle pause must not expire the 320 ns watchdog or revive data.
      scenario <= 25; wait for 1 ps; snapshot("SHORT_PAUSE_BEFORE");
      clock_run <= '0'; wait for 120 ns; snapshot("SHORT_PAUSE_STOPPED");
      clock_run <= '1'; wait for 300 ns; snapshot("SHORT_PAUSE_RECOVERED");
      for p in 0 to 7 loop burst(1+p,p,NOMINAL_ENTRY); end loop;
      for p in 0 to 7 loop burst(9+p,p,EARLY_STRESS); end loop;
      reset_with_stopped_clock(17);
      burst(18,0,NOMINAL_ENTRY);
      burst(19,3,NOMINAL_ENTRY,1);
      recover_epoch(23,true);
      burst(20,4,NOMINAL_ENTRY);
      burst(21,6,NOMINAL_ENTRY,2);
      recover_epoch(24);
      burst(22,7,NOMINAL_ENTRY);
      event_line("DONE",22,"00"); done <= '1';
      report "DPHY_RATE93_STIMULUS_DONE" severity note;
      wait;
   end process;
end;
