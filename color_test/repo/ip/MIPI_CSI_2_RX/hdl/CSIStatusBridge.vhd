-- Coherent, requested status snapshots. Reuse the vendor bundled-data
-- handshake; never sample binary counters independently across clocks.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
library xpm;
use xpm.vcomponents.all;

entity CSIStatusBridge is
  port (
    SourceClk : in std_logic;
    SourcePackets, SourceCrc : in std_logic_vector(31 downto 0);
    DestClk, DestResetn, Request : in std_logic;
    Busy : out std_logic;
    Packets, Crc, SnapshotSequence : out std_logic_vector(31 downto 0)
  );
end entity;

architecture rtl of CSIStatusBridge is
  signal held, received : std_logic_vector(63 downto 0) := (others => '0');
  signal send, acknowledged, ready, acknowledge : std_logic := '0';
  signal state : natural range 0 to 3 := 0;
  signal serial : unsigned(31 downto 0) := (others => '0');
  signal publish_pending : std_logic := '0';
begin
  SnapshotCDC : xpm_cdc_handshake
    generic map (DEST_EXT_HSK => 1, DEST_SYNC_FF => 2, SRC_SYNC_FF => 2,
                 INIT_SYNC_FF => 1, SIM_ASSERT_CHK => 1, WIDTH => 64)
    port map (src_clk => SourceClk, src_in => held, src_send => send,
              src_rcv => acknowledged, dest_clk => DestClk,
              dest_out => received, dest_req => ready, dest_ack => acknowledge);

  -- Complete every outstanding transfer even across the consumer reset. The
  -- stopped source retains its request/data; no reset can tear the held word.
  process(SourceClk)
  begin
    if rising_edge(SourceClk) then
      if send = '0' and acknowledged = '0' then
        held <= SourcePackets & SourceCrc;
        send <= '1';
      elsif send = '1' and acknowledged = '1' then
        send <= '0';
      end if;
    end if;
  end process;

  process(DestClk)
  begin
    if rising_edge(DestClk) then
      case state is
        when 0 =>
          if Request = '1' and DestResetn = '1' then
            state <= 1; publish_pending <= '1';
          end if;
        when 1 =>
          -- Drain the previously held snapshot first. Only the next transfer
          -- can certify source progress after this request.
          if ready = '1' then acknowledge <= '1'; state <= 2; end if;
        when 2 =>
          if ready = '0' then acknowledge <= '0'; state <= 3; end if;
        when 3 =>
          if ready = '1' then
            if DestResetn = '1' and publish_pending = '1' then
              Packets <= received(63 downto 32);
              Crc <= received(31 downto 0);
              serial <= serial + 1;
            end if;
            state <= 0;
          end if;
      end case;
      -- Reset the published status, not an in-flight vendor handshake.
      if DestResetn = '0' then
        Packets <= (others => '0'); Crc <= (others => '0');
        serial <= (others => '0');
        publish_pending <= '0';
      end if;
    end if;
  end process;
  SnapshotSequence <= std_logic_vector(serial);
  Busy <= '1' when state /= 0 else '0';
end architecture;
