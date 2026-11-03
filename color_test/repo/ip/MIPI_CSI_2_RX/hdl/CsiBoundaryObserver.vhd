-- Source-clock passive boundary observation and first-fault retention.
-- CSI and VDMA taps MUST share Clk; the integration checks their BD clock net.
-- Resetn is the external video reset, deliberately not CSI's soft reset, so
-- the frozen evidence survives CSI disable/reset during capture cleanup.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity CsiBoundaryObserver is
  port (
    Clk, Resetn, Arm, Freeze : in std_logic;
    FsEvent, FeEvent : in std_logic;
    CsiValid, CsiReady, CsiSof, CsiEol : in std_logic;
    VdmaValid, VdmaReady, VdmaSof, VdmaEol : in std_logic;
    VdmaKeep : in std_logic_vector(2 downto 0);
    Overflow : in std_logic;
    Words : out std_logic_vector(767 downto 0)
  );
end entity;

architecture rtl of CsiBoundaryObserver is
  signal csi_words, vdma_words : std_logic_vector(255 downto 0);
  signal csi_fault, vdma_fault : std_logic_vector(7 downto 0);
  signal probe_enable, keep_error : std_logic;
  signal armed, frozen, freeze_pending : std_logic := '0';
  signal tick, fs_count, fe_count, arm_sequence : unsigned(31 downto 0) := (others => '0');
  signal reason, raw_strobes, held_strobes : std_logic_vector(31 downto 0) := (others => '0');
  signal live_words, frozen_words : std_logic_vector(767 downto 0) := (others => '0');
begin
  -- Pending immediately closes both observers after the offending edge.
  -- The next clock can therefore copy POST-event words without counting the
  -- following edge, even when Valid/Ready stay asserted continuously.
  probe_enable <= armed and not frozen and not freeze_pending;
  keep_error <= '0' when VdmaKeep = "111" else '1';

  CsiProbe: entity work.AxisBoundaryProbe
    generic map (ExpectedBeats => 320, ExpectedLines => 720)
    port map (Clk => Clk, Resetn => Resetn, Arm => Arm, Enable => probe_enable,
              Valid => CsiValid, Ready => CsiReady, Sof => CsiSof, Eol => CsiEol,
              KeepError => '0', Words => csi_words, Fault => csi_fault);
  VdmaProbe: entity work.AxisBoundaryProbe
    generic map (ExpectedBeats => 1280, ExpectedLines => 720)
    port map (Clk => Clk, Resetn => Resetn, Arm => Arm, Enable => probe_enable,
              Valid => VdmaValid, Ready => VdmaReady, Sof => VdmaSof, Eol => VdmaEol,
              KeepError => keep_error, Words => vdma_words, Fault => vdma_fault);

  -- Raw signal levels at the first-fault edge, not a handshake count:
  -- [3:0] CSI EOL/SOF/READY/VALID, [7:4] VDMA EOL/SOF/READY/VALID,
  -- [10:8] VDMA KEEP, [11] overflow, [12] decoded FS, [13] decoded FE.
  Raw: process(CsiValid, CsiReady, CsiSof, CsiEol, VdmaValid, VdmaReady,
               VdmaSof, VdmaEol, VdmaKeep, Overflow, FsEvent, FeEvent)
    variable v : std_logic_vector(31 downto 0);
  begin
    v := (others => '0');
    v(0) := CsiValid; v(1) := CsiReady; v(2) := CsiSof; v(3) := CsiEol;
    v(4) := VdmaValid; v(5) := VdmaReady; v(6) := VdmaSof; v(7) := VdmaEol;
    v(10 downto 8) := VdmaKeep;
    v(11) := Overflow; v(12) := FsEvent; v(13) := FeEvent;
    raw_strobes <= v;
  end process;

  Live: process(armed, frozen, freeze_pending, reason, tick, fs_count,
                fe_count, arm_sequence, raw_strobes, held_strobes,
                csi_words, vdma_words)
    variable v : std_logic_vector(767 downto 0);
    variable flags : std_logic_vector(31 downto 0);
  begin
    v := (others => '0');
    flags := (others => '0');
    flags(0) := frozen;
    flags(1) := armed;
    v(31 downto 0) := x"42564F31"; -- boundary observation ABI BVO1
    v(63 downto 32) := flags;
    v(95 downto 64) := reason;
    v(127 downto 96) := std_logic_vector(tick);
    v(159 downto 128) := std_logic_vector(fs_count);
    v(191 downto 160) := std_logic_vector(fe_count);
    v(223 downto 192) := std_logic_vector(arm_sequence);
    if freeze_pending = '1' or frozen = '1' then
      v(255 downto 224) := held_strobes;
    else
      v(255 downto 224) := raw_strobes;
    end if;
    v(511 downto 256) := csi_words;
    v(767 downto 512) := vdma_words;
    live_words <= v;
  end process;

  Retain: process(Clk)
    variable why : std_logic_vector(31 downto 0);
    variable snapshot : std_logic_vector(767 downto 0);
  begin
    if rising_edge(Clk) then
      if Resetn = '0' then
        armed <= '0'; frozen <= '0'; freeze_pending <= '0';
        tick <= (others => '0'); fs_count <= (others => '0'); fe_count <= (others => '0');
        arm_sequence <= (others => '0'); reason <= (others => '0');
        held_strobes <= (others => '0'); frozen_words <= (others => '0');
      elsif Arm = '1' then
        armed <= '1'; frozen <= '0'; freeze_pending <= '0';
        tick <= (others => '0'); fs_count <= (others => '0'); fe_count <= (others => '0');
        arm_sequence <= arm_sequence + 1;
        reason <= (others => '0'); held_strobes <= (others => '0');
      elsif freeze_pending = '1' then
        -- Probe words/global counters now include exactly the fault edge.
        snapshot := live_words;
        snapshot(32) := '1';
        frozen_words <= snapshot;
        frozen <= '1';
        freeze_pending <= '0';
      elsif armed = '1' and frozen = '0' then
        tick <= tick + 1;
        if FsEvent = '1' then fs_count <= fs_count + 1; end if;
        if FeEvent = '1' then fe_count <= fe_count + 1; end if;
        why := (others => '0');
        why(7 downto 0) := csi_fault;
        why(15 downto 8) := vdma_fault;
        why(16) := Overflow;
        if why /= x"00000000" or Freeze = '1' then
          -- A simultaneous hardware event takes precedence over a software
          -- request. Freeze never overwrites an already retained first fault.
          if why = x"00000000" then why(31) := '1'; end if;
          reason <= why;
          held_strobes <= raw_strobes;
          freeze_pending <= '1';
        end if;
      end if;
    end if;
  end process;

  Words <= frozen_words when frozen = '1' else live_words;
end architecture;
