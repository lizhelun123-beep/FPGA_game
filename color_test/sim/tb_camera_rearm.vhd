-- The byte observations are an unmodified contiguous native-clock ILA window.
-- RefClk LP is a declared reconstruction, not a simultaneous RefClk recording.
-- Only ISERDES data outputs are forced; the complete lane control/reset path runs.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use ieee.std_logic_textio.all;
use work.DphyDebugLib.all;

entity tb_camera_rearm is end;
architecture test of tb_camera_rearm is
  constant PERIOD:time:=85_714_288 fs;
  signal bc,sc:std_logic:='0';
  signal cc:std_logic_vector(0 to 2):=(others=>'0');
  signal lp:std_logic_vector(7 downto 0):=x"ff";
  signal clp:std_logic_vector(3 downto 0):=x"f";
  type lane_bytes is array(0 to 1) of std_logic_vector(7 downto 0);
  type replica_bytes is array(0 to 2) of lane_bytes;
  type replica_bits is array(0 to 2) of std_logic_vector(1 downto 0);
  type lane_debug is array(0 to 1) of DebugSFEN_Type;
  type replica_debug is array(0 to 2) of lane_debug;
  signal data_out:replica_bytes;
  signal valid,active:replica_bits;
  signal dbg:replica_debug;
  signal trace_index:integer:=-1;
  signal done:boolean:=false;
begin
  bc<=not bc after PERIOD/2;
  sc<=not sc after PERIOD/8;
  clocks:for replica in 0 to 2 generate
    process
    begin
      wait for replica*2 ns;
      loop cc(replica)<='0';wait for 2.5 ns;
        cc(replica)<='1';wait for 2.5 ns;end loop;
    end process;
    lanes:for lane in 0 to 1 generate
      dut:entity work.DPHY_LaneSFEN
        generic map(kNoLP=>true,kRefClkFreqHz=>200_000_000)
        port map(dLP0_in=>"000000"&lp(lane*4+1 downto lane*4),
          dLP1_in=>"000000"&lp(lane*4+3 downto lane*4+2),
          dLP0_out=>open,dLP1_out=>open,
          cLP_in=>clp(lane*2+1 downto lane*2),cLP_out=>open,
          aLP=>"11",aHS=>'0',RefClk=>cc(replica),SerClkHS=>sc,DivClk=>bc,
          cRxClkActiveHS=>'1',RxByteClkHS=>open,
          rbRxDataHS=>data_out(replica)(lane),rbRxValidHS=>valid(replica)(lane),
          rbRxActiveHS=>active(replica)(lane),rbRxSyncHS=>open,
          rbErrSotHS=>open,rbErrSotSyncHS=>open,
          aEnable=>'1',aForceRxmode=>'0',aStopstate=>open,
          aErrEsc=>open,aErrControl=>open,debug=>dbg(replica)(lane));
    end generate;
  end generate;
  process
    file f:text open read_mode is "replay_control.txt";
    variable l:line;variable index:integer;variable p:std_logic_vector(7 downto 0);
  begin
    while not endfile(f) loop
      wait until falling_edge(bc);readline(f,l);read(l,index);hread(l,p);
      trace_index<=index;lp<=p;
    end loop;
    wait until falling_edge(bc);done<=true;wait;
  end process;
  process
    file f:text open read_mode is "ref_lp_control.txt";
    variable l:line;variable t:time;variable p:std_logic_vector(3 downto 0);
  begin
    while not endfile(f) loop
      readline(f,l);read(l,t);hread(l,p);
      assert t>=now report "REARM_REF_EVENT_ORDER" severity failure;
      wait for t-now;clp<=p;
    end loop;
    wait;
  end process;
  process
    file f:text open write_mode is "ppi_observed.txt";
    variable l:line;
    procedure field(variable row:inout line;value:integer) is
    begin write(row,value);write(row,string'(" "));end;
    function as_int(value:std_logic) return integer is
    begin if value='1' then return 1;else return 0;end if;end;
  begin
    while not done loop
      wait until rising_edge(bc);wait for 1 fs;
      if trace_index>=0 then
        for replica in 0 to 2 loop
          field(l,replica);field(l,trace_index);
          for lane in 0 to 1 loop
            field(l,as_int(valid(replica)(lane)));
            hwrite(l,data_out(replica)(lane));write(l,string'(" "));
            field(l,as_int(active(replica)(lane)));
            field(l,as_int(dbg(replica)(lane).cHSReset));
            field(l,as_int(dbg(replica)(lane).cHSSettled));
            field(l,as_int(dbg(replica)(lane).dSyncHard));
            field(l,as_int(dbg(replica)(lane).dSyncSoft));
            field(l,as_int(dbg(replica)(lane).dSyncErr));
          end loop;
          writeline(f,l);
        end loop;
      end if;
    end loop;
    report "REARM_REPLAY_COMPLETED full lane FSM/reset/drain feedback; byte trace unchanged";
    std.env.finish;wait;
  end process;
end;
