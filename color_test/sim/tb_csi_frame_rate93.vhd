-- Production CSI core and the existing generated vendor FIFOs. PPI-level test:
-- the separately signed PHY serial timing is not re-signed by this fixture.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;

entity tb_csi_frame_rate93 is end;
architecture test of tb_csi_frame_rate93 is
  constant BYTE_PERIOD : time := 85714288 fs;
  constant VIDEO_PERIOD : time := 6666666 fs;
  type bytes_t is array(natural range <>) of std_logic_vector(7 downto 0);
  signal bc, vc : std_logic := '0';
  signal byte_run : boolean := true;
  signal rstn, en : std_logic := '0';
  signal clk_active : std_logic := '1';
  signal clk_stop : std_logic := '0';
  signal data : std_logic_vector(15 downto 0) := (others=>'0');
  signal valid, active, sync, den : std_logic_vector(1 downto 0) := "00";
  signal cen, ovf : std_logic;
  signal vd : std_logic_vector(39 downto 0);
  signal vv, vl, ready : std_logic := '0';
  signal vu : std_logic_vector(0 downto 0);
  signal crc_count, packet_count : std_logic_vector(31 downto 0);
  signal hold_output, require_hidden : boolean := false;
  signal epoch : natural := 1;
  signal stage : natural := 0;
  signal frames, pixels : natural := 0;
  function pixel(e,y,x:natural) return natural is
  begin return (e*17+y*13+x*7) mod 1024; end;
  -- CSI-2 header ECC parity membership, D0 first, P0 in bit0.
  function ecc(h:std_logic_vector(23 downto 0)) return std_logic_vector is
    type ns is array(0 to 23) of natural;
    constant masks:ns := (7,11,13,14,19,21,22,25,26,28,35,37,38,41,42,44,49,50,52,56,31,47,55,59);
    variable p:unsigned(7 downto 0):=(others=>'0');
  begin
    for i in 0 to 23 loop
      if h(i)='1' then p:=p xor to_unsigned(masks(i),8); end if;
    end loop;
    return std_logic_vector(p);
  end;
begin
  vc <= not vc after VIDEO_PERIOD/2;
  process begin
    wait for BYTE_PERIOD/2;
    if byte_run then bc<=not bc; else bc<='0'; end if;
  end process;
  dut: entity work.MIPI_CSI2_Rx
    generic map(kLaneCount=>2,kDebug=>false)
    port map(RxByteClkHS=>bc,aClkStopstate=>clk_stop,aRxClkActiveHS=>clk_active,
      rbRxDataHS=>data,rbRxSyncHS=>sync,rbRxValidHS=>valid,rbRxActiveHS=>active,
      aDEnable=>den,aClkEnable=>cen,video_aclk=>vc,video_aresetn=>rstn,vEnable=>en,
      m_axis_video_tdata=>vd,m_axis_video_tvalid=>vv,m_axis_video_tready=>ready,
      m_axis_video_tlast=>vl,m_axis_video_tuser=>vu,
      CrcErrorCount=>crc_count,FrameCount=>packet_count,FifoOverflow=>ovf);

  -- One scoreboard consumes only handshakes, checks all four 10-bit pixels,
  -- SOF/EOL, and every held response. Expected data comes from image geometry.
  process(vc)
    variable n,x,y,c,seen_frames:natural:=0;
    variable stalled:boolean:=false;
    variable held:std_logic_vector(41 downto 0);
    variable got:std_logic_vector(41 downto 0);
  begin
    if rising_edge(vc) then
      c:=c+1;
      ready<='1';
      if hold_output or c mod 127 < 8 then ready<='0'; end if;
      got:=vu & vl & vd;
      if rstn='0' then
        n:=0; stalled:=false;
      else
        if stalled then
          assert vv='1' and got=held report "CSI_FRAME_FAIL held AXI response changed stage=" & integer'image(stage) severity failure;
        end if;
        if require_hidden then
          assert vv='0' report "CSI_FRAME_FAIL stale output after disable/loss stage=" & integer'image(stage) &
            " valid=" & std_logic'image(vv) & " sof=" & std_logic'image(vu(0)) & " eol=" & std_logic'image(vl) &
            " data=" & to_hstring(vd) & " en=" & std_logic'image(en) & " byte=" & std_logic'image(bc) &
            " packets=" & to_hstring(packet_count) & " crc=" & to_hstring(crc_count) severity failure;
        end if;
        if vv='1' and ready='1' then
          x:=n mod 1280; y:=n/1280;
          assert y<720 report "CSI_FRAME_FAIL excess pixels" severity failure;
          assert (vu(0)='1')=(n=0) report "CSI_FRAME_FAIL SOF n=" & integer'image(n) severity failure;
          assert (vl='1')=(x=1276) report "CSI_FRAME_FAIL EOL n=" & integer'image(n) severity failure;
          for i in 0 to 3 loop
            assert unsigned(vd(i*10+9 downto i*10))=pixel(epoch,y,x+i)
              report "CSI_FRAME_FAIL pixel n=" & integer'image(n+i) & " got=" & to_hstring(vd) severity failure;
          end loop;
          n:=n+4;
          if n=1280*720 then
            n:=0; seen_frames:=seen_frames+1; frames<=seen_frames;
            report "CSI_FRAME_COMPLETE epoch=" & integer'image(epoch) & " pixels=921600 lines=720";
          end if;
          pixels<=pixels+4;
        end if;
        stalled:=vv='1' and ready='0' and not require_hidden;
        held:=got;
      end if;
    end if;
  end process;

  process
    procedure tick(n:natural) is
    begin for i in 1 to n loop wait until falling_edge(bc); end loop; end;
    procedure packet(p:bytes_t) is
    begin
      tick(1); active<="11"; sync<="11"; tick(1); sync<="00";
      for i in 0 to p'length/2-1 loop
        data<=p(2*i+1)&p(2*i); valid<="11"; tick(1);
      end loop;
      valid<="00"; active<="00"; tick(16);
    end;
    procedure short_packet(dt,id:natural) is
      variable p:bytes_t(0 to 3);
    begin
      p(0):=std_logic_vector(to_unsigned(dt,8));
      p(1):=std_logic_vector(to_unsigned(id mod 256,8));
      p(2):=std_logic_vector(to_unsigned(id/256,8));
      p(3):=ecc(p(2)&p(1)&p(0)); packet(p);
    end;
    procedure line(e,y:natural; corrupt_crc:boolean:=false) is
      variable p:bytes_t(0 to 1605);
      variable v,l:natural;
      variable crc:unsigned(15 downto 0):=x"FFFF";
      variable feedback:std_logic;
    begin
      p(0):=x"2B"; p(1):=x"40"; p(2):=x"06"; p(3):=ecc(p(2)&p(1)&p(0));
      for g in 0 to 319 loop
        l:=0;
        for i in 0 to 3 loop
          v:=pixel(e,y,g*4+i);
          p(4+g*5+i):=std_logic_vector(to_unsigned(v/4,8)); l:=l+(v mod 4)*2**(i*2);
        end loop;
        p(8+g*5):=std_logic_vector(to_unsigned(l,8));
      end loop;
      for b in 4 to 1603 loop
        for j in 0 to 7 loop
          feedback:=crc(0) xor p(b)(j); crc:=shift_right(crc,1);
          if feedback='1' then crc:=crc xor x"8408"; end if;
        end loop;
      end loop;
      p(1604):=std_logic_vector(crc(7 downto 0)); p(1605):=std_logic_vector(crc(15 downto 8));
      if corrupt_crc then p(1604):=p(1604) xor x"01"; end if;
      packet(p);
    end;
    procedure frame(e:natural) is
    begin
      short_packet(0,e);
      for y in 0 to 719 loop line(e,y); end loop;
      short_packet(1,e); wait for 20 us;
      report "CSI_FRAME_STATS epoch=" & integer'image(e) & " packets=" & to_hstring(packet_count) &
        " crc=" & to_hstring(crc_count) & " overflow=" & std_logic'image(ovf);
      assert frames=e report "CSI_FRAME_FAIL incomplete frame epoch=" & integer'image(e) severity failure;
      assert unsigned(packet_count)=720 report "CSI_FRAME_FAIL long-packet count=" & to_hstring(packet_count) severity failure;
      assert unsigned(crc_count)=0 and ovf='0'
        report "CSI_FRAME_FAIL CRC/overflow crc=" & to_hstring(crc_count) & " ovf=" & std_logic'image(ovf) severity failure;
    end;
  begin
    report "CSI_FRAME_BEGIN rate=93.333333Mb/s PPI byte=11.666666MHz video=150MHz actual vendor FIFOs";
    wait for 4 us; rstn<='1'; en<='1'; tick(32); stage<=1;
    frame(1);
    report "CSI_FRAME_GATE continuous full frame and bounded AXI backpressure passed";
    -- Reset while byte clock is stopped; release may only complete on recovery.
    stage<=2; rstn<='0'; en<='0'; byte_run<=false; wait for 4 us;
    rstn<='1'; wait for 4 us;
    byte_run<=true; en<='1'; epoch<=2; tick(32); frame(2);
    report "CSI_FRAME_GATE stopped-clock reset release and fresh full frame passed";
    -- Enable is not the reset contract. Preserve an established stalled AXI
    -- beat on disable, then explicitly reset the receive epoch before reuse.
    stage<=3; rstn<='0'; wait for 4 us; rstn<='1'; tick(32);
    epoch<=3; hold_output<=true; short_packet(0,3); line(3,0); wait for 2 us;
    assert vv='1' report "CSI_FRAME_FIXTURE no buffered line before disable" severity failure;
    en<='0'; wait for 2 us;
    report "CSI_FRAME_OBSERVATION enable-only disable does not certify FIFO flush";
    rstn<='0'; byte_run<=false; wait for 4 us;
    rstn<='1'; require_hidden<=true; hold_output<=false; wait for 4 us;
    byte_run<=true; en<='1'; tick(32); require_hidden<=false; frame(3);
    report "CSI_FRAME_GATE explicit reset discarded buffered old line despite stopped byte clock";
    stage<=4; rstn<='0'; wait for 4 us; rstn<='1'; epoch<=4; tick(32);
    short_packet(0,4); line(4,0,true); short_packet(1,4); wait for 20 us;
    report "CSI_FRAME_STATS negative_crc packets=" & to_hstring(packet_count) & " crc=" & to_hstring(crc_count);
    assert unsigned(packet_count)=1 and unsigned(crc_count)=1 and ovf='0'
      report "CSI_FRAME_FAIL corrupted CRC not counted exactly once" severity failure;
    assert frames=3 report "CSI_FRAME_FAIL partial negative image accepted as full frame" severity failure;
    report "CSI_FRAME_OBSERVATION_COMPLETE";
    finish;
  end process;
  process begin wait for 180 ms; assert false report "CSI_FRAME_FAIL timeout" severity failure; end process;
end;
