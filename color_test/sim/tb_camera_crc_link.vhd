-- Connected canonical serial PHY -> CSI packet CRC regression; no alternate receiver.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
entity tb_camera_crc_link is generic(PHASE_COVERAGE:boolean:=false);end;entity tb_camera_crc_link_phases is end;architecture test of tb_camera_crc_link_phases isbegin dut:entity work.tb_camera_crc_link generic map(PHASE_COVERAGE=>true);end;
architecture test of tb_camera_crc_link is
 constant UI:time:=10_714_286 fs;
 type bytes_t is array(natural range <>) of std_logic_vector(7 downto 0);
 signal refclk,txclk,byteclk,ddrclk,ready,clock_stop,vc:std_logic:='0';
 signal clock_run:std_logic:='0';
 signal rst:std_logic:='1'; signal rstn,en:std_logic:='0';
 signal clock_lp,lp0,lp1:std_logic_vector(1 downto 0):="11";
 signal serial_data:std_logic_vector(1 downto 0):="00";
 signal data:std_logic_vector(15 downto 0);
 signal valid,active,sync,soterr,softerr,den:std_logic_vector(1 downto 0);
 signal cen,ovf:std_logic;
 signal vd:std_logic_vector(39 downto 0);signal vv,vl:std_logic;
 signal vu:std_logic_vector(0 downto 0);
 signal crc_count,packet_count:std_logic_vector(31 downto 0);
 signal source_tick:natural:=0;
 signal expected:bytes_t(0 to 1605):=(others=>x"00");
 signal trail_value:std_logic_vector(1 downto 0):="11";
 signal expected_length:natural:=0;signal packet_id:natural:=0;
 signal ppi_bytes,pixels:natural:=0;
 function pixel(y,x:natural) return natural is
 begin return (17+y*13+x*7) mod 1024;end;
 function ecc(h:std_logic_vector(23 downto 0)) return std_logic_vector is
  type ns is array(0 to 23) of natural;
  constant masks:ns:=(7,11,13,14,19,21,22,25,26,28,35,37,38,41,42,44,49,50,52,56,31,47,55,59);
  variable p:unsigned(7 downto 0):=(others=>'0');
 begin for i in 0 to 23 loop if h(i)='1' then p:=p xor to_unsigned(masks(i),8);end if;end loop;return std_logic_vector(p);end;
begin
 refclk<=not refclk after 2.5 ns;vc<=not vc after 3_500_000 fs;
 process begin wait for UI;if clock_run='1' then txclk<=not txclk;source_tick<=source_tick+1;else txclk<='0';end if;end process;
   phy: entity work.MIPI_DPHY_Receiver
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
         aClkEnable => cen, aD0Enable => den(0), aD1Enable => den(1),
         aClkForceRxmode => '0', aD0ForceRxmode => '0', aD1ForceRxmode => '0',
         rbD0RxDataHS => data(7 downto 0), rbD1RxDataHS => data(15 downto 8),
         rbD0RxValidHS => valid(0), rbD1RxValidHS => valid(1),
         rbD0RxActiveHS => active(0), rbD1RxActiveHS => active(1),
         rbD0RxSyncHS => sync(0), rbD1RxSyncHS => sync(1),
         rbD0ErrSotHS => soterr(0), rbD1ErrSotHS => soterr(1),
         rbD0ErrSotSyncHS => softerr(0), rbD1ErrSotSyncHS => softerr(1),
         s_axi_lite_aclk => refclk, s_axi_lite_aresetn => rstn,
         s_axi_lite_awaddr => "0000", s_axi_lite_awprot => "000",
         s_axi_lite_awvalid => '0', s_axi_lite_wdata => (others => '0'),
         s_axi_lite_wstrb => "1111", s_axi_lite_wvalid => '0',
         s_axi_lite_bready => '1', s_axi_lite_araddr => "0000",
         s_axi_lite_arprot => "000", s_axi_lite_arvalid => '0', s_axi_lite_rready => '1');
 csi:entity work.MIPI_CSI2_Rx generic map(kLaneCount=>2,kDebug=>false)
 port map(RxByteClkHS=>byteclk,aClkStopstate=>clock_stop,aRxClkActiveHS=>ready,
 rbRxDataHS=>data,rbRxSyncHS=>sync,rbRxValidHS=>valid,rbRxActiveHS=>active,
 aDEnable=>den,aClkEnable=>cen,video_aclk=>vc,video_aresetn=>rstn,vEnable=>en,
 m_axis_video_tdata=>vd,m_axis_video_tvalid=>vv,m_axis_video_tready=>'1',
 m_axis_video_tlast=>vl,m_axis_video_tuser=>vu,CrcErrorCount=>crc_count,FrameCount=>packet_count,FifoOverflow=>ovf);
 process(byteclk)
  variable id,n:natural:=0;variable b:std_logic_vector(7 downto 0);
 begin if rising_edge(byteclk) then
  if packet_id/=id then n:=0;id:=packet_id;end if;
  for lane in 0 to 1 loop if valid(lane)='1' then
   b:=data(lane*8+7 downto lane*8);
   if n<expected_length then
    assert b=expected(n) report "PPI_BYTE_MISMATCH id="&integer'image(id)&" byte="&integer'image(n)&" got="&to_hstring(b)&" expected="&to_hstring(expected(n)) severity failure;
   else assert b=(b'range=>trail_value(lane)) report "Unexpected serial trailer byte" severity failure;end if;
   n:=n+1;
  end if;end loop;ppi_bytes<=n;
 end if;end process;
 process(vc)
  variable n,x,y,v:natural:=0;
 begin if rising_edge(vc) and vv='1' then
  for i in 0 to 3 loop
   x:=n mod 1280;y:=n/1280;v:=to_integer(unsigned(vd(10*i+9 downto 10*i)));
   assert v=pixel(y,x) report "PIXEL_MISMATCH index="&integer'image(n) severity failure;
   n:=n+1;
  end loop;pixels<=n;
 end if;end process;
 process
  procedure bits(v:std_logic_vector(1 downto 0)) is begin serial_data<=v;wait for UI;end;
  procedure bytes(a,b:std_logic_vector(7 downto 0)) is begin for i in 0 to 7 loop bits(b(i)&a(i));end loop;end;
  procedure packet(p:bytes_t) is
  begin
   packet_id<=packet_id+1;expected_length<=p'length;
   for i in p'range loop expected(i)<=p(i);end loop;
   lp0<="11";lp1<="11";serial_data<="00";wait for 2 us;
   lp0<="01";lp1<="01";wait for 80 ns;
   wait until source_tick mod 8=0;wait for 7 ns;
   lp0<="00";lp1<="00";wait for 200 ns+9*UI;   if PHASE_COVERAGE then    wait for (packet_id mod 8)*UI;    report "SERIAL_PHASE_UI="&integer'image(packet_id mod 8);   end if;   bytes(x"B8",x"B8");
   for i in 0 to p'length/2-1 loop bytes(p(i*2),p(i*2+1));end loop;
   trail_value<=not p(p'high)(7)&not p(p'high-1)(7);
   for i in 1 to 12 loop bits(not p(p'high)(7)&not p(p'high-1)(7));end loop;
   lp0<="11";lp1<="11";wait for 3 us;
   assert ppi_bytes>=p'length report "PPI_TRUNCATED" severity failure;
   report "PPI_PACKET_OK id="&integer'image(packet_id)&" prefix_bytes="&integer'image(p'length)&" observed="&integer'image(ppi_bytes);
  end;
  procedure line(y:natural;bad:boolean:=false) is
   variable p:bytes_t(0 to 1605);variable v,l:natural;variable crc:unsigned(15 downto 0):=x"FFFF";variable fb:std_logic;
  begin
   p(0):=x"2B";p(1):=x"40";p(2):=x"06";p(3):=ecc(p(2)&p(1)&p(0));
   for g in 0 to 319 loop l:=0;for i in 0 to 3 loop v:=pixel(y,g*4+i);p(4+g*5+i):=std_logic_vector(to_unsigned(v/4,8));l:=l+(v mod 4)*2**(i*2);end loop;p(8+g*5):=std_logic_vector(to_unsigned(l,8));end loop;
   for b in 4 to 1603 loop for j in 0 to 7 loop fb:=crc(0) xor p(b)(j);crc:=shift_right(crc,1);if fb='1' then crc:=crc xor x"8408";end if;end loop;end loop;
   p(1604):=std_logic_vector(crc(7 downto 0));p(1605):=std_logic_vector(crc(15 downto 8));if bad then p(1604):=p(1604) xor x"01";end if;packet(p);
  end;
  variable fs:bytes_t(0 to 3):=(x"00",x"01",x"00",x"00");
 begin
  wait for 1 us;rst<='0';rstn<='1';en<='1';wait for 1 us;
  clock_lp<="01";wait for 60 ns;clock_lp<="00";wait for 450 ns;
  clock_run<='1';wait for 113 us;
  fs(3):=ecc(fs(2)&fs(1)&fs(0));packet(fs);
  if PHASE_COVERAGE then   for y in 0 to 6 loop line(y);end loop;   wait for 3 us;   assert unsigned(packet_count)=7 and unsigned(crc_count)=0 and ovf='0' and pixels=8960 report "PHASE_POSITIVE_CRC_OR_PIXELS_FAIL" severity failure;   line(7,true);wait for 3 us;   assert unsigned(packet_count)=8 and unsigned(crc_count)=1 and ovf='0' and pixels=10240 report "PHASE_NEGATIVE_CRC_FAIL" severity failure;   report "CAMERA_CRC_LINK_PHASE_PASS all8 phases all10240 pixels CRC7good1bad";  else  line(0);line(1);wait for 3 us;
  report "POSITIVE packets="&to_hstring(packet_count)&" CRC="&to_hstring(crc_count)&" pixels="&integer'image(pixels);
  assert unsigned(packet_count)=2 and unsigned(crc_count)=0 and ovf='0' and pixels=2560 report "POSITIVE_CRC_OR_PIXELS_FAIL" severity failure;
  line(2,true);wait for 3 us;
  assert unsigned(packet_count)=3 and unsigned(crc_count)=1 and ovf='0' and pixels=3840 report "NEGATIVE_CRC_FAIL" severity failure;  end if;
  report "CAMERA_CRC_LINK_PASS";std.env.finish;wait;
 end process;
 process begin  if PHASE_COVERAGE then wait for 1200 us;else wait for 600 us;end if;  assert false report "CRC_LINK_TIMEOUT" severity failure; end process;
end;
