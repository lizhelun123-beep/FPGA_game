-- Replay real ISERDES/LP observations into the canonical byte pipeline.
-- The serial primitive output alone is forced;the actual align/valid HDL runs.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use ieee.std_logic_textio.all;

entity tb_camera_crc_tail is end;
architecture test of tb_camera_crc_tail is
  constant PERIOD:time:=85_714_288 fs;
  signal bc,sc,cc:std_logic:='0';
  signal rst:std_logic:='1';
  signal lp:std_logic_vector(7 downto 0):=x"00";
  type byte_pair is array(0 to 1) of std_logic_vector(7 downto 0);
  signal output:byte_pair;
  signal valid:std_logic_vector(1 downto 0);
  signal case_id:natural:=0;
  signal done:boolean:=false;
  type packet_t is array(0 to 1605) of std_logic_vector(7 downto 0);
  type packets_t is array(1 to 3) of packet_t;
begin
  bc<=not bc after PERIOD/2;
  sc<=not sc after PERIOD/8;
  cc<=not cc after 2.5 ns;
  lanes:for lane in 0 to 1 generate
    dut:entity work.HS_Deserializer
      generic map(kNoLP=>true,kExternalByteReset=>true)
      port map(dLP0_in=>"000000"&lp(lane*4+1 downto lane*4),
        dLP1_in=>"000000"&lp(lane*4+3 downto lane*4+2),
        dLP0_out=>open,dLP1_out=>open,SerClk=>sc,DivClk=>bc,
        aHSIn=>'0',aLPIn=>"00",aLPOut=>open,dDataOut8=>output(lane),
        dDataOut9=>open,dValid=>valid(lane),dDrainBusy=>open,
        dSyncHard=>open,dSyncSoft=>open,dSyncErr=>open,CtlClk=>cc,
        cIDLY_LD=>'0',cIDLY_CE=>'0',cIDLY_INC=>'0',cIDLY_CNT=>open,
        aRst=>rst,aSettled=>'1');
  end generate;
  process
    file f:text open read_mode is "replay_control.txt";
    variable l:line;variable r,id:integer;variable p:std_logic_vector(7 downto 0);
  begin
    while not endfile(f) loop
      wait until falling_edge(bc);readline(f,l);read(l,r);hread(l,p);read(l,id);
      if r=0 then rst<='0';else rst<='1';end if;
      lp<=p;case_id<=id;
    end loop;
    wait until falling_edge(bc);case_id<=0;done<=true;wait;
  end process;
  process
    file f:text open read_mode is "replay_expected.txt";
    variable l:line;variable e:packets_t;variable v,b:std_logic_vector(7 downto 0);
    type counts_t is array(1 to 3) of natural;
    variable counts:counts_t:=(others=>0);variable id:natural;
  begin
    for c in 1 to 3 loop
      for i in 0 to 1605 loop readline(f,l);hread(l,v);e(c)(i):=v;end loop;
    end loop;
    while not done loop
      wait until rising_edge(bc);wait for 1 fs;id:=case_id;
      if id/=0 then
        for lane in 0 to 1 loop
          if valid(lane)='1' then
            for k in 0 to 7 loop b(k):=output(lane)(7-k);end loop;
            assert counts(id)<1606 report "TAIL_REPLAY_EXCESS" severity failure;
            assert b=e(id)(counts(id)) report "TAIL_REPLAY_BYTE_MISMATCH case="&integer'image(id)&" byte="&integer'image(counts(id)) severity failure;
            counts(id):=counts(id)+1;
          end if;
        end loop;
      end if;
    end loop;
    for c in 1 to 3 loop
      report "TAIL_REPLAY_COUNT case="&integer'image(c)&" bytes="&integer'image(counts(c));
    end loop;
    assert counts=(1606,1606,1606) report "TAIL_REPLAY_TRUNCATED" severity failure;
    report "TAIL_REPLAY_PASS exact1606 bytes including independently verified CRC in all3 real packets";
    std.env.finish;wait;
  end process;
end;
