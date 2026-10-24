-- Existing LLP and actual generated vendor FIFOs; legal input packets and
-- downstream stalls only. No force, alternate parser, or ideal FIFO model.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.CsiDebugLib.all;

entity tb_csi_frame_boundary is
  generic (HEIGHT : positive := 8; STRESS_TAIL : boolean := true);
end;
architecture test of tb_csi_frame_boundary is
  constant WIDTH : positive := 1280;
  constant BYTE_PERIOD : time := 85714288 fs;
  constant VIDEO_PERIOD : time := 7000000 fs; -- actual ~142.857MHz video
  type bytes_t is array(natural range <>) of std_logic_vector(7 downto 0);
  signal bc, vc : std_logic := '0';
  signal rst : std_logic := '1';
  signal sd : std_logic_vector(31 downto 0) := (others=>'0');
  signal sk : std_logic_vector(3 downto 0) := (others=>'0');
  signal sv, sr, sl : std_logic := '0';
  signal vd : std_logic_vector(39 downto 0);
  signal vv, vr, vl, ovf : std_logic := '0';
  signal vu : std_logic_vector(0 downto 0);
  signal crc_count, packet_count : std_logic_vector(31 downto 0);
  signal dbg : DebugLLP_t;
  signal release_output, seek_tail, tail_held : boolean := false;
  signal got_pixels, tail_transfers, errors : natural := 0;
  function pixel(e,y,x:natural) return natural is
  begin return (e*17+y*13+x*7) mod 1024; end;
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
  bc <= not bc after BYTE_PERIOD/2;
  vc <= not vc after VIDEO_PERIOD/2;
  dut: entity work.LLP
    port map(SAxisClk=>bc,sAxisTdata=>sd,sAxisTkeep=>sk,
      sAxisTvalid=>sv,sAxisTready=>sr,sAxisTlast=>sl,MAxisClk=>vc,
      mAxisTdata=>vd,mAxisTvalid=>vv,mAxisTready=>vr,mAxisTlast=>vl,
      mAxisTuser=>vu,sOverflow=>ovf,aRst=>rst,CrcErrorCount=>crc_count,
      FrameCount=>packet_count,dbgLLP=>dbg);

  process(vc)
    variable c,n,e,y,x,bad,tails:natural:=0;
    variable reg_stalled,fmt_stalled,out_stalled:boolean:=false;
    variable reg_held:std_logic_vector(37 downto 0);
    variable fmt_held,out_held:std_logic_vector(41 downto 0);
    procedure check(ok:boolean; label_text:string) is
    begin
      if not ok then
        if bad<12 then report "BOUNDARY_ERROR " & label_text severity warning; end if;
        bad:=bad+1;
      end if;
    end;
  begin
    if rising_edge(vc) then
      c:=c+1;
      vr<='0';
      if rst='1' then
        n:=0; bad:=0; tails:=0;
        reg_stalled:=false; fmt_stalled:=false; out_stalled:=false;
        tail_held<=false;
      else
        if release_output then
          if c mod 127>=8 and c mod 257>=19 then vr<='1'; end if;
        elsif STRESS_TAIL and not seek_tail then
          -- Leave about the real line-FIFO capacity (2048 beats), not a
          -- whole eight-line image, queued when the input reaches its tail.
          -- CDC FIFO is only 32 words and must never be overrun by the fixture.
          if n < WIDTH*HEIGHT-2060*4 then vr<='1'; end if;
        elsif seek_tail and not tail_held then
          if tails=HEIGHT-1 and dbg.mReg_Tvalid='1' and
             dbg.mReg_Tlast='1' and dbg.mReg_Tready='0' then
            tail_held<=true;
            report "BOUNDARY_TAIL_HELD tails=" & integer'image(tails);
          elsif c mod 32=0 then vr<='1'; end if;
        end if;
        check(ovf='0',"input overflow");
        if reg_stalled then
          check(dbg.mReg_Tvalid='1' and
            (dbg.mReg_Tuser & dbg.mReg_Tlast & dbg.mReg_Tkeep & dbg.mReg_Tdata)=reg_held,
            "blocked packet register changed SOF/data");
        end if;
        if fmt_stalled then
          check(dbg.mFmt_Tvalid='1' and
            (dbg.mFmt_Tuser & dbg.mFmt_Tlast & dbg.mFmt_Tdata)=fmt_held,
            "blocked formatter changed");
        end if;
        if out_stalled then
          check(vv='1' and (vu & vl & vd)=out_held,"blocked output changed");
        end if;
        if dbg.mReg_Tvalid='1' and dbg.mReg_Tready='1' and dbg.mReg_Tlast='1' then
          tails:=tails+1;
        end if;
        if vv='1' and vr='1' then
          e:=n/(WIDTH*HEIGHT)+1; y:=(n/WIDTH) mod HEIGHT; x:=n mod WIDTH;
          check((vu(0)='1')=(x=0 and y=0),"SOF pixel=" & integer'image(n));
          check((vl='1')=(x=WIDTH-4),"EOL pixel=" & integer'image(n));
          for i in 0 to 3 loop
            check(unsigned(vd(i*10+9 downto i*10))=pixel(e,y,x+i),
              "pixel=" & integer'image(n+i));
          end loop;
          n:=n+4;
        end if;
        reg_stalled:=dbg.mReg_Tvalid='1' and dbg.mReg_Tready='0';
        reg_held:=dbg.mReg_Tuser & dbg.mReg_Tlast & dbg.mReg_Tkeep & dbg.mReg_Tdata;
        fmt_stalled:=dbg.mFmt_Tvalid='1' and dbg.mFmt_Tready='0';
        fmt_held:=dbg.mFmt_Tuser & dbg.mFmt_Tlast & dbg.mFmt_Tdata;
        out_stalled:=vv='1' and vr='0'; out_held:=vu & vl & vd;
      end if;
      got_pixels<=n; tail_transfers<=tails; errors<=bad;
    end if;
  end process;

  process
    procedure tick(n:natural) is
    begin for i in 1 to n loop wait until falling_edge(bc); end loop; end;
    procedure packet(p:bytes_t) is
      variable word:std_logic_vector(31 downto 0);
      variable keep:std_logic_vector(3 downto 0);
    begin
      for w in 0 to (p'length+3)/4-1 loop
        word:=(others=>'0'); keep:=(others=>'0');
        for b in 0 to 3 loop
          if w*4+b<p'length then
            word(b*8+7 downto b*8):=p(w*4+b); keep(b):='1';
          end if;
        end loop;
        sd<=word; sk<=keep; sv<='1'; sl<='0';
        if w=(p'length+3)/4-1 then sl<='1'; end if;
        wait until rising_edge(bc);
        assert sr='1' report "BOUNDARY_FIXTURE input FIFO capacity exceeded" severity failure;
        wait until falling_edge(bc); sv<='0'; sl<='0'; tick(1);
      end loop;
      tick(16);
    end;
    procedure short_packet(dt,id:natural) is
      variable p:bytes_t(0 to 3);
    begin
      p(0):=std_logic_vector(to_unsigned(dt,8));
      p(1):=std_logic_vector(to_unsigned(id mod 256,8));
      p(2):=std_logic_vector(to_unsigned(id/256,8));
      p(3):=ecc(p(2)&p(1)&p(0)); packet(p);
    end;
    procedure line(e,y:natural; corrupt:boolean:=false) is
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
      if corrupt then crc:=crc xor x"0001"; end if;
      p(1604):=std_logic_vector(crc(7 downto 0)); p(1605):=std_logic_vector(crc(15 downto 8));
      packet(p);
    end;
  begin
    wait for 4 us; rst<='0'; tick(64);
    if not STRESS_TAIL then release_output<=true; end if;
    short_packet(0,1);
    for y in 0 to HEIGHT-1 loop line(1,y); end loop;
    if STRESS_TAIL then
      seek_tail<=true;
      wait until tail_held for 2 ms;
      assert tail_held report "BOUNDARY_FIXTURE no held final payload tails=" &
        integer'image(tail_transfers) & " pixels=" & integer'image(got_pixels) &
        " reg=" & std_logic'image(dbg.mReg_Tvalid) & std_logic'image(dbg.mReg_Tlast) &
        std_logic'image(dbg.mReg_Tready) severity failure;
    end if;
    short_packet(1,1); short_packet(0,2); wait for 4 us;
    release_output<=true;
    for y in 0 to HEIGHT-1 loop
      line(2,y); -- RAW10 CRC tail is still checked under all stalls
    end loop;
    short_packet(1,2); wait for 100 us;
    report "BOUNDARY_SUMMARY pixels=" & integer'image(got_pixels) &
      " errors=" & integer'image(errors) & " packets=" & to_hstring(packet_count) &
      " crc=" & to_hstring(crc_count) & " overflow=" & std_logic'image(ovf);
    assert got_pixels=WIDTH*HEIGHT*2 and errors=0 and
      unsigned(packet_count)=HEIGHT*2 and unsigned(crc_count)=0
      report "BOUNDARY_FAIL clean two-frame/CRC contract" severity failure;
    -- A deliberate CRC mutation must remain visible; it may not be hidden by
    -- deferring the completed-packet comparison.
    short_packet(0,3); line(3,0,true); short_packet(1,3); wait for 100 us;
    assert unsigned(packet_count)=HEIGHT*2+1 and unsigned(crc_count)=1
      report "BOUNDARY_FAIL CRC negative control" severity failure;
    report "BOUNDARY_PASS geometry+stable sidebands+CRC tail+corrupt CRC detection";
    finish;
  end process;
  process begin wait for 130 ms; assert false report "BOUNDARY_FAIL timeout" severity failure; end process;
end;
