-- Passive AXI-video geometry observer. No output participates in stream control.
-- Fault predicts an offending accepted beat from the state BEFORE the active
-- clock edge; Words exposes the registered state AFTER that beat. A parent may
-- disable Enable on the following cycle and snapshot Words on the next edge.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity AxisBoundaryProbe is
  generic (
    ExpectedBeats : positive := 320;
    ExpectedLines : positive := 720
  );
  port (
    Clk, Resetn, Arm, Enable : in std_logic;
    Valid, Ready, Sof, Eol, KeepError : in std_logic;
    Words : out std_logic_vector(255 downto 0);
    Fault : out std_logic_vector(7 downto 0)
  );
end entity;

architecture rtl of AxisBoundaryProbe is
  subtype word_t is unsigned(31 downto 0);
  type words_t is array (0 to 7) of word_t;
  signal counters, next_counters : words_t := (others => (others => '0'));
  signal seen_sof, next_seen_sof : std_logic := '0';
begin
  -- Word 0 SOF count; 1 accepted EOL total; 2 current-frame EOL count;
  -- 3 current-line accepted beats; 4 last-line beats; 5 previous-frame lines;
  -- 6/7 minimum/maximum accepted line length since Arm. A zero minimum means
  -- that no line has completed. On a partial-line SOF fault, word 4 instead
  -- retains that interrupted line's length (Fault bit 2), before the new SOF
  -- starts word 3 at one. All counters are unsigned modulo 2**32.
  Outputs: for i in 0 to 7 generate
    Words(32*i+31 downto 32*i) <= std_logic_vector(counters(i));
  end generate;

  Predict: process(counters, seen_sof, Enable, Valid, Ready, Sof, Eol, KeepError)
    variable v : words_t;
    variable seen : std_logic;
    variable bad : std_logic_vector(7 downto 0);
    variable interrupted_line : boolean;
  begin
    v := counters;
    seen := seen_sof;
    bad := (others => '0');
    interrupted_line := false;
    if Enable = '1' and Valid = '1' and Ready = '1' then
      if Sof = '1' then
        if seen = '1' then
          if v(2) /= to_unsigned(ExpectedLines, 32) then bad(1) := '1'; end if;
          if v(3) /= 0 then
            bad(2) := '1';
            v(4) := v(3);
            interrupted_line := true;
          end if;
          v(5) := v(2);
        end if;
        seen := '1';
        v(0) := v(0) + 1;
        v(2) := (others => '0');
        v(3) := (others => '0');
      end if;
      -- Ignore a partial leading frame until its first accepted SOF. SOF is
      -- itself the first data beat of the new frame, including SOF+EOL beats.
      if seen = '1' then
        v(3) := v(3) + 1;
        if KeepError = '1' then bad(4) := '1'; end if;
        if Eol = '1' then
          if v(3) /= to_unsigned(ExpectedBeats, 32) then bad(0) := '1'; end if;
          -- Preserve the older interrupted line even if this offending SOF
          -- also carries EOL. The reason bits distinguish this special case.
          if not interrupted_line then v(4) := v(3); end if;
          if v(1) = 0 or v(3) < v(6) then v(6) := v(3); end if;
          if v(3) > v(7) then v(7) := v(3); end if;
          v(1) := v(1) + 1;
          v(2) := v(2) + 1;
          if v(2) > to_unsigned(ExpectedLines, 32) then bad(3) := '1'; end if;
          v(3) := (others => '0');
        elsif v(3) > to_unsigned(ExpectedBeats, 32) then
          -- Also retain an overlong line which never produces EOL.
          bad(5) := '1';
        end if;
      end if;
    end if;
    next_counters <= v;
    next_seen_sof <= seen;
    Fault <= bad;
  end process;

  Registers: process(Clk)
  begin
    if rising_edge(Clk) then
      if Resetn = '0' or Arm = '1' then
        counters <= (others => (others => '0'));
        seen_sof <= '0';
      else
        counters <= next_counters;
        seen_sof <= next_seen_sof;
      end if;
    end if;
  end process;
end architecture;
