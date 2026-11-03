-- Directed observer-only simulation. It drives no production AXI/DMA owner.
-- Compile AxisBoundaryProbe.vhd then CsiBoundaryObserver.vhd before this TB.
-- A completed run emits BOUNDARY_OBSERVER_TB_PASS; the finite clock then stops.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_CsiBoundaryObserver is
end entity;

architecture test of tb_CsiBoundaryObserver is
  signal clk : std_logic := '0';
  signal done : boolean := false;
  signal resetn, arm, freeze : std_logic := '0';
  signal fs, fe, cv, cr, cs, ce, dv, dr, ds, de, overflow : std_logic := '0';
  signal keep : std_logic_vector(2 downto 0) := "111";
  signal words : std_logic_vector(767 downto 0);
  function w(data : std_logic_vector; index : natural) return unsigned is
  begin
    return unsigned(data(32*index+31 downto 32*index));
  end function;
begin
  clk <= not clk after 5 ns when not done else '0';
  Dut: entity work.CsiBoundaryObserver
    port map (Clk => clk, Resetn => resetn, Arm => arm, Freeze => freeze,
              FsEvent => fs, FeEvent => fe,
              CsiValid => cv, CsiReady => cr, CsiSof => cs, CsiEol => ce,
              VdmaValid => dv, VdmaReady => dr, VdmaSof => ds, VdmaEol => de,
              VdmaKeep => keep, Overflow => overflow, Words => words);

  Stimulus: process
    variable saved : std_logic_vector(767 downto 0);
    variable epoch : unsigned(31 downto 0);
    procedure edge is
    begin
      wait until rising_edge(clk);
      wait for 1 ns;
    end procedure;
    procedure idle is
    begin
      cv <= '0'; cs <= '0'; ce <= '0'; dv <= '0'; ds <= '0'; de <= '0';
      fs <= '0'; fe <= '0'; freeze <= '0'; overflow <= '0'; keep <= "111";
    end procedure;
    procedure rearm is
    begin
      idle;
      arm <= '1'; edge;
      arm <= '0'; edge;
      assert words(32) = '0' and words(33) = '1' report "Arm flags" severity failure;
      assert w(words, 8) = 0 and w(words, 16) = 0 report "Arm clears probes" severity failure;
      assert w(words, 2) = 0 report "Arm clears first reason" severity failure;
    end procedure;
    procedure csi_line(beats : positive; first : boolean) is
    begin
      cr <= '1'; cv <= '1';
      for beat in 1 to beats loop
        cs <= '0'; ce <= '0';
        if first and beat = 1 then cs <= '1'; end if;
        if beat = beats then ce <= '1'; end if;
        edge;
      end loop;
      idle;
    end procedure;
  begin
    edge; resetn <= '1'; edge;
    assert words(31 downto 0) = x"42564F31" report "ABI magic" severity failure;
    assert words(33 downto 32) = "00" report "No automatic arm" severity failure;
    rearm;
    -- Start both frames, then hold what would be an illegal SOF+EOL/KEEP beat
    -- under backpressure. Neither strobes nor lengths may advance on a stall.
    cv <= '1'; cr <= '1'; cs <= '1'; dv <= '1'; dr <= '1'; ds <= '1'; edge;
    cv <= '1'; cs <= '1'; ce <= '1'; cr <= '0';
    dv <= '1'; ds <= '1'; de <= '1'; dr <= '0'; keep <= "000";
    for i in 1 to 4 loop edge; end loop;
    assert w(words, 8) = 1 and w(words, 16) = 1 and w(words, 11) = 1 and
           w(words, 19) = 1 and w(words, 2) = 0
      report "Stalled strobes changed state" severity failure;
    rearm;

    -- One complete simultaneous 720-line frame. CSI has four pixels/beat;
    -- VDMA is 24-bit one pixel/beat, so their accepted line lengths differ.
    fs <= '1'; edge; fs <= '0'; cr <= '1'; dr <= '1';
    for line in 1 to 720 loop
      for beat in 1 to 1280 loop
        cv <= '0'; cs <= '0'; ce <= '0'; dv <= '1'; ds <= '0'; de <= '0';
        if beat <= 320 then cv <= '1'; end if;
        if line = 1 and beat = 1 then cs <= '1'; ds <= '1'; end if;
        if beat = 320 then ce <= '1'; end if;
        if beat = 1280 then de <= '1'; end if;
        edge;
      end loop;
    end loop;
    idle; fe <= '1'; edge; fe <= '0';
    assert words(32) = '0' and w(words, 9) = 720 and w(words, 17) = 720
      report "Correct frame was rejected" severity failure;
    assert w(words, 14) = 320 and w(words, 15) = 320 and
           w(words, 22) = 1280 and w(words, 23) = 1280
      report "Accepted line lengths" severity failure;
    cv <= '1'; cs <= '1'; dv <= '1'; ds <= '1'; fs <= '1'; edge; idle; edge;
    assert words(32) = '0' and w(words, 13) = 720 and w(words, 21) = 720
      report "Correct frame-to-frame boundary" severity failure;
    assert w(words, 4) = 2 and w(words, 5) = 1 report "Decoded FS/FE counters" severity failure;

    rearm;
    -- Every accepted short line must retain its offending post-edge length.
    csi_line(319, true);
    -- This following accepted beat must be excluded by freeze_pending.
    cv <= '1'; cs <= '1'; edge; idle; edge;
    assert words(32) = '1' and words(64) = '1' report "Short-line fault" severity failure;
    assert w(words, 12) = 319 and w(words, 9) = 1 and w(words, 8) = 1
      report "Short-line snapshot omitted event or included next beat" severity failure;
    saved := words;
    cv <= '1'; cs <= '1'; ce <= '1'; fs <= '1'; overflow <= '1'; freeze <= '1';
    for i in 1 to 5 loop edge; end loop;
    assert words = saved report "First fault overwritten" severity failure;

    epoch := w(words, 6); rearm;
    assert w(words, 6) = epoch + 1 report "Arm sequence" severity failure;
    csi_line(320, true); edge;
    cv <= '1'; cs <= '1'; cr <= '1'; edge; idle; edge;
    assert words(32) = '1' and words(65) = '1' report "Early SOF fault" severity failure;
    assert w(words, 8) = 2 and w(words, 13) = 1 and w(words, 11) = 1
      report "Early SOF post-event snapshot" severity failure;

    rearm;
    cv <= '1'; cr <= '1';
    for beat in 1 to 73 loop
      cs <= '0';
      if beat = 1 then cs <= '1'; end if;
      edge;
    end loop;
    cs <= '1'; edge; idle; edge;
    assert words(32) = '1' and words(66) = '1' and w(words, 12) = 73 and
           w(words, 11) = 1
      report "Partial-line SOF lost the interrupted length" severity failure;

    rearm;
    dr <= '1'; dv <= '1';
    for beat in 1 to 1279 loop
      ds <= '0'; de <= '0';
      if beat = 1 then ds <= '1'; end if;
      if beat = 1279 then de <= '1'; end if;
      edge;
    end loop;
    idle; edge;
    assert words(32) = '1' and words(72) = '1' and w(words, 20) = 1279
      report "VDMA short-line fault" severity failure;

    rearm;
    -- Software freeze includes the command edge but excludes every later beat.
    freeze <= '1'; fs <= '1'; cv <= '1'; cs <= '1'; cr <= '1'; edge;
    freeze <= '0'; fs <= '0'; cs <= '0'; edge; idle;
    assert words(32) = '1' and words(95) = '1' report "Software freeze reason" severity failure;
    assert w(words, 4) = 1 and w(words, 8) = 1 and w(words, 11) = 1
      report "Software freeze edge was not atomic" severity failure;
    saved := words; for i in 1 to 3 loop edge; end loop;
    assert words = saved report "Software freeze not retained" severity failure;

    rearm;
    dv <= '1'; dr <= '1'; ds <= '1'; keep <= "011"; edge; idle; edge;
    assert words(32) = '1' and words(76) = '1' report "Accepted KEEP fault" severity failure;

    rearm;
    overflow <= '1'; edge; idle; edge;
    assert words(32) = '1' and words(80) = '1' report "Overflow first fault" severity failure;
    report "BOUNDARY_OBSERVER_TB_PASS" severity note;
    done <= true;
    wait;
  end process;
end architecture;
