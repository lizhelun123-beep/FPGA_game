// Presentation policy only; all geometry, timer and results come from C.
export function modelsForDisplay(models, referenceModels = []) {
  return models.map(object => {
    if (object.type !== 'SOURCE' || (object.tip && object.direction)) return object;
    // C uses the emitter point as SOURCE.center and exports no preview-only
    // nozzle/body coordinates. Use the same level's configured visual source.
    const source = referenceModels.find(value => value.type === 'SOURCE' && value.logical_emitter);
    if (!object.logical_emitter || !source?.tip || !source?.direction) {
      throw new Error('光源显示数据不完整，请返回菜单重新选择关卡。');
    }
    return {...object, center: source.center, axis: source.axis,
      tip: source.tip, direction: source.direction};
  });
}

export function runningScene(record) {
  return Boolean(record && !record.preview && record.screen === 'game' && record.game_state === 2);
}

export function canStart(record, backendConnected) {
  return Boolean(backendConnected && record.connected && !record.preview &&
    record.game_state === 1 && record.board_phase === 'READY' && record.board_ready);
}

export function showSuccess(record, backendConnected) {
  return Boolean(backendConnected && record.valid && record.state === 'LIVE' &&
    !record.display_held && record.success);
}

export function backendGap(record) {
  const keep = runningScene(record) || record.screen === 'result' || record.preview;
  return {...record, models: keep ? record.models : [], segments: keep ? record.segments : [],
    valid: false, success: false, ready: false, board_ready: false, connected: false,
    state: 'DISCONNECTED', display_held: runningScene(record),
    display_status: '后端连接断开 · 等待重连'};
}
