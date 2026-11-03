import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { createPortalPair } from './portals.js';
import { runningScene, canStart, showSuccess, backendGap, modelsForDisplay } from './presentation.js';

const SCALE = 0.01;
const BEAM_HEIGHT = 1.15;
const viewport = document.querySelector('#viewport');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#1c2932');
scene.fog = new THREE.Fog('#1c2932', 27, 65);
let renderer, composer, camera, controls, data, modelGroup, portals;
let currentLevel = 0, disposed = false, renderedFrames = 0;
let socket, reconnectTimer, connected = false, lastPacket = 0, snapshot = null, signature = '';
let geometryDim = 1;
let displayedGeometryKey = '';
let errorActive = false, pendingMenu = false, pendingQuit = false;
let hoverDemo = null;
const modelsByType = new Map();
let beamGroup;
const rayMeshes = [];
const beamAxis = new THREE.Vector3(0, 1, 0);
const rayDelta = new THREE.Vector3();

const MENU_PREVIEW_WIDTH = 480;
const MENU_PREVIEW_HEIGHT = 270;
const HOVER_CAPTURE_INTERVAL_MS = 50;
const HOVER_ROTATION_SPEED = 0.42;
const HOVER_TARGET = new THREE.Vector3(0, 0.3, -0.2);

const beamMaterials = [];
const staticResources = new Set();

function material(color, roughness = 0.55, metalness = 0.3) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

function box(parent, size, position, mat) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
  mesh.position.set(...position);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function cylinder(parent, radius, depth, position, mat, direction = null) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, depth, 32), mat);
  mesh.position.set(...position);
  if (direction) mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}

function point(p, y = BEAM_HEIGHT) {
  return new THREE.Vector3((p[0] - data.width / 2) * SCALE, y, (p[1] - data.height / 2) * SCALE);
}

function concreteTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1024;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(1024, 1024);
  let seed = 107;
  for (let i = 0; i < img.data.length; i += 4) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const n = 148 + (seed >>> 26) * 0.32;
    img.data[i] = n - 6; img.data[i + 1] = n; img.data[i + 2] = n + 2; img.data[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  // Low-contrast mineral patches keep the panels from looking like flat plastic.
  for (let i = 0; i < 230; i++) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const x = seed % 1024;
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const y = seed % 1024, radius = 12 + ((seed >>> 12) % 96);
    const patch = ctx.createRadialGradient(x, y, 0, x, y, radius);
    patch.addColorStop(0, i % 3 ? 'rgba(33,43,47,0.045)' : 'rgba(225,232,232,0.065)');
    patch.addColorStop(1, 'rgba(90,100,106,0)');
    ctx.fillStyle = patch; ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
  for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
    const px = x * 256, py = y * 256;
    const gradient = ctx.createLinearGradient(px, py, px + 256, py + 256);
    gradient.addColorStop(0, 'rgba(35,47,52,0.10)');
    gradient.addColorStop(0.5, 'rgba(190,202,204,0.04)');
    gradient.addColorStop(1, 'rgba(20,31,38,0.12)');
    ctx.fillStyle = gradient; ctx.fillRect(px, py, 256, 256);
    ctx.strokeStyle = '#39454b'; ctx.lineWidth = 2; ctx.strokeRect(px + 1, py + 1, 254, 254);
    ctx.strokeStyle = '#bdc4c6'; ctx.lineWidth = 1; ctx.strokeRect(px + 3, py + 3, 250, 250);
    ctx.fillStyle = '#6a767c';
    for (const [dx, dy] of [[12, 12], [244, 12], [12, 244], [244, 244]]) {
      ctx.beginPath(); ctx.arc(px + dx, py + dy, 1.3, 0, Math.PI * 2); ctx.fill();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  staticResources.add(texture);
  return texture;
}

function buildRoom() {
  const room = new THREE.Group();
  scene.add(room);
  const width = data.width * SCALE, depth = data.height * SCALE;
  const dark = material('#26353e', 0.47, 0.72);
  const trim = material('#c1c9cb', 0.6, 0.35);
  const concrete = new THREE.MeshStandardMaterial({ color: '#a2a9a9', map: concreteTexture(), roughness: 0.82, metalness: 0.08 });
  const wallMat = concrete.clone();
  wallMat.color.set('#657b86');
  const floorMat = concrete.clone();
  floorMat.color.set('#354750');
  box(room, [width + 0.36, 0.32, depth + 0.36], [0, -0.21, 0], dark);
  const top = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), concrete);
  top.rotation.x = -Math.PI / 2; top.receiveShadow = true; room.add(top);
  for (const z of [-depth / 2 - 0.035, depth / 2 + 0.035]) box(room, [width + 0.14, 0.035, 0.07], [0, -0.004, z], trim);
  for (const x of [-width / 2 - 0.035, width / 2 + 0.035]) box(room, [0.07, 0.035, depth], [x, -0.004, 0], trim);
  for (const x of [-width / 2 + 0.65, 0, width / 2 - 0.65]) {
    for (const z of [-depth / 2 + 0.55, depth / 2 - 0.55]) {
      box(room, [0.24, 2.3, 0.24], [x, -1.5, z], dark);
      box(room, [0.56, 0.09, 0.52], [x, -2.66, z], dark);
    }
    box(room, [0.16, 0.18, depth - 0.7], [x, -1.92, 0], dark);
  }
  for (let x = -5.8; x <= 5.8; x += 0.95) {
    box(room, [0.72, 0.22, 0.06], [x, -0.31, depth / 2 + 0.17], material('#141f28', 0.5, 0.65));
    for (const dx of [-0.28, 0.28]) {
      cylinder(room, 0.022, 0.018, [x + dx, -0.29, depth / 2 + 0.21], trim, new THREE.Vector3(0, 0, 1));
    }
  }
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(48, 40), floorMat);
  floor.rotation.x = -Math.PI / 2; floor.position.y = -2.72; floor.receiveShadow = true; room.add(floor);
  // Single-sided walls leave the table visible when the user orbits outside the room.
  const back = new THREE.Mesh(new THREE.PlaneGeometry(27, 15), wallMat);
  back.position.set(0, 3, -7); back.receiveShadow = true; room.add(back);
  const side = new THREE.Mesh(new THREE.PlaneGeometry(30, 15), wallMat);
  side.rotation.y = Math.PI / 2; side.position.set(-10, 3, 3); side.receiveShadow = true; room.add(side);
  const lamp = new THREE.MeshStandardMaterial({ color: '#dbf3ff', emissive: '#ceeaff', emissiveIntensity: 2.8, roughness: 0.3 });
  for (const x of [-8, -4, 1, 6, 10]) {
    box(room, [0.2, 9, 0.16], [x, 2.1, -6.88], dark);
    box(room, [0.12, 1.6, 0.05], [x, 2.4, -6.75], lamp);
    box(room, [0.32, 0.05, 0.25], [x, 1.56, -6.8], dark);
  }
  for (let x = -8; x <= 8; x += 2) {
    box(room, [0.06, 1.2, 0.06], [x, -1.8, -5.1], dark);
  }
  box(room, [16, 0.05, 0.05], [0, -1.2, -5.1], trim);
  box(room, [16, 0.04, 0.04], [0, -1.7, -5.1], dark);
  const hemi = new THREE.HemisphereLight('#bfe5ff', '#30363b', 1.7);
  scene.add(hemi);
  const key = new THREE.DirectionalLight('#ebf5ff', 3.1);
  key.position.set(1, 11, 6); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.left = -11; key.shadow.camera.right = 11;
  key.shadow.camera.top = 10; key.shadow.camera.bottom = -10;
  key.shadow.camera.near = 0.5; key.shadow.camera.far = 35;
  key.shadow.bias = -0.00015; key.shadow.normalBias = 0.025;
  scene.add(key);
  const fill = new THREE.DirectionalLight('#7dacc5', 1.15);
  fill.position.set(-7, 4, -4); scene.add(fill);
}

function makeObject(object, ray) {
  const group = new THREE.Group();
  group.position.copy(point(object.center, 0));
  group.rotation.y = -Math.atan2(object.axis[1], object.axis[0]);
  group.name = object.type;
  const length = object.size[0] * SCALE, width = object.size[1] * SCALE;
  const white = material('#c5d0d2', 0.39, 0.55);
  const dark = material('#18242c', 0.38, 0.8);
  const silver = material('#7d929f', 0.25, 0.88);
  box(group, [length + 0.06, 0.07, width + 0.06], [0, 0.045, 0], dark);
  if (object.type === 'SOURCE') {
    box(group, [length * 0.68, 0.72, width * 0.72], [-length * 0.04, 0.47, 0], white);
    box(group, [length * 0.7, 0.06, width * 0.77], [-length * 0.04, 0.81, 0], dark);
    for (const z of [-width * 0.37, width * 0.37]) box(group, [length * 0.4, 0.44, 0.008], [-length * 0.04, 0.47, z], dark);
    box(group, [length * 0.8, 0.44, width], [-length * 0.04, BEAM_HEIGHT - 0.02, 0], white);
    for (const z of [-width / 2 - 0.003, width / 2 + 0.003]) {
      for (let i = 0; i < 4; i++) box(group, [0.017, 0.17, 0.008], [-length * 0.25 + i * 0.048, BEAM_HEIGHT, z], dark);
    }
    const localTip = new THREE.Vector3((object.tip[0] - object.center[0]) * SCALE, BEAM_HEIGHT,
      (object.tip[1] - object.center[1]) * SCALE).applyAxisAngle(new THREE.Vector3(0, 1, 0), -group.rotation.y);
    const localDirection = new THREE.Vector3(object.direction[0], 0, object.direction[1])
      .applyAxisAngle(new THREE.Vector3(0, 1, 0), -group.rotation.y).normalize();
    for (const [radius, offset, depth, mat] of [[0.18, -0.11, 0.13, dark], [0.142, -0.035, 0.08, silver], [0.108, -0.009, 0.02, dark]]) {
      cylinder(group, radius, depth, localTip.clone().addScaledVector(localDirection, offset).toArray(), mat, localDirection);
    }
    cylinder(group, 0.055, 0.006, localTip.toArray(), new THREE.MeshBasicMaterial({ color: new THREE.Color(6, 0.12, 0.04), toneMapped: false }), localDirection);
    box(group, [0.09, 0.013, 0.09], [-0.07, BEAM_HEIGHT + 0.21, 0], new THREE.MeshBasicMaterial({ color: '#f9895f' }));
  } else if (object.type === 'TARGET') {
    // The C target is a circular receiver in the ground plane: preserve that footprint.
    const radius = length / 2;
    cylinder(group, radius, 0.77, [0, 0.48, 0], dark);
    cylinder(group, radius, 0.52, [0, BEAM_HEIGHT, 0], white);
    cylinder(group, radius + 0.003, 0.16, [0, BEAM_HEIGHT, 0], dark);
    const signal = new THREE.MeshBasicMaterial({ color: ray.success ? new THREE.Color(0.25, 2.3, 0.7) : new THREE.Color('#4c6970'), toneMapped: false });
    group.userData.signal = signal;
    cylinder(group, radius + 0.005, 0.034, [0, BEAM_HEIGHT, 0], signal);
    cylinder(group, radius * 0.76, 0.04, [0, BEAM_HEIGHT + 0.28, 0], dark);
    cylinder(group, radius * 0.24, 0.045, [0, BEAM_HEIGHT + 0.3, 0], signal);
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      cylinder(group, 0.024, 0.037, [Math.cos(a) * radius * 0.84, BEAM_HEIGHT + 0.27, Math.sin(a) * radius * 0.84], silver);
      if (i % 2 === 0) {
        const rib = box(group, [0.065, 0.7, 0.065], [Math.cos(a) * radius * 0.82, 0.48, Math.sin(a) * radius * 0.82], white);
        rib.rotation.y = -a;
      }
    }
  } else if (object.type === 'MIRROR') {
    for (const x of [-length * 0.42, length * 0.42]) {
      box(group, [0.1, 0.6, width * 0.8], [x, 0.38, 0], dark);
    }
    const mirror = new THREE.MeshPhysicalMaterial({ color: '#a6d6e3', metalness: 0.95, roughness: 0.12, clearcoat: 1, side: THREE.DoubleSide });
    const face = new THREE.Mesh(new THREE.PlaneGeometry(length, 1.35), mirror);
    face.position.y = BEAM_HEIGHT; group.add(face);
    for (const y of [BEAM_HEIGHT - 0.69, BEAM_HEIGHT + 0.69]) box(group, [length + 0.1, 0.05, width], [0, y, 0], silver);
    for (const x of [-length / 2 - 0.035, length / 2 + 0.035]) box(group, [0.055, 1.42, width], [x, BEAM_HEIGHT, 0], dark);
    const stripe = new THREE.MeshBasicMaterial({ color: '#9bd8e9', transparent: true, opacity: 0.38, side: THREE.DoubleSide });
    for (const x of [-length * 0.2, length * 0.15]) {
      const glint = new THREE.Mesh(new THREE.PlaneGeometry(0.025, 1.25), stripe);
      glint.position.set(x, BEAM_HEIGHT, 0.002); glint.rotation.z = -0.24; group.add(glint);
    }
  } else if (object.type === 'WALL') {
    box(group, [length, 1.65, width], [0, 0.89, 0], white);
    box(group, [length, 0.08, width + 0.01], [0, 1.72, 0], dark);
  }
  group.userData.success = Boolean(ray.success);
  return group;
}

function makeBeamPool() {
  const group = new THREE.Group(); group.name = 'rays';
  const core = new THREE.MeshBasicMaterial({ color: new THREE.Color(7.5, 0.32, 0.1), toneMapped: false });
  const halo = new THREE.MeshBasicMaterial({ color: '#ff3020', transparent: true, opacity: 0.11, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
  beamMaterials.push(halo);
  for (let i = 0; i < data.maxVisibleSegments; i++) {
    const segment = new THREE.Group();
    const bodies = [];
    for (const [radius, mat] of [[0.008, core], [0.025, halo], [0.055, halo]]) {
      const beam = cylinder(segment, radius, 1, [0, 0, 0], mat);
      beam.castShadow = false; beam.receiveShadow = false; bodies.push(beam);
    }
    const end = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 8), core);
    segment.add(end);
    const glow = new THREE.PointLight('#ff3824', 0.9, 1.3, 2);
    segment.add(glow); segment.visible = false; group.add(segment);
    rayMeshes.push({group: segment, bodies, end, glow});
  }
  return group;
}

function updateGeometry(models, segments, levelId, success = false) {
  const nextSignature = JSON.stringify([levelId, models.map(object => [object.type, object.size])]);
  if (nextSignature !== signature) {
    portals?.dispose(); portals = null;
    disposeGroup(modelGroup); modelsByType.clear();
    beamMaterials.length = 0; rayMeshes.length = 0;
    modelGroup = new THREE.Group(); modelGroup.name = 'level';
    for (const object of models) {
      if (!object.type.startsWith('PORTAL_')) {
        const mesh = makeObject(object, {success});
        modelsByType.set(object.type, mesh); modelGroup.add(mesh);
      }
    }
    beamGroup = makeBeamPool(); modelGroup.add(beamGroup); scene.add(modelGroup);
    const pair = models.filter(object => object.type.startsWith('PORTAL_'));
    if (pair.length === 2) portals = createPortalPair(scene, pair, {
      width: data.width, height: data.height, scale: SCALE, beamHeight: BEAM_HEIGHT,
    });
    signature = nextSignature; geometryDim = -1;
  }
  for (const object of models) {
    const mesh = modelsByType.get(object.type);
    if (!mesh) continue;
    mesh.position.copy(point(object.center, 0));
    mesh.rotation.y = -Math.atan2(object.axis[1], object.axis[0]);
    if (mesh.userData.signal && mesh.userData.success !== Boolean(success)) {
      mesh.userData.success = Boolean(success);
      mesh.userData.signal.color.copy(success ? new THREE.Color(0.25, 2.3, 0.7) : new THREE.Color('#4c6970'));
      mesh.userData.signal.userData.baseColor = mesh.userData.signal.color.clone();
      geometryDim = -1;
    }
  }
  portals?.setModels(models);
  for (let i = 0; i < rayMeshes.length; i++) {
    const mesh = rayMeshes[i], segment = segments[i];
    mesh.group.visible = Boolean(segment);
    if (!segment) continue;
    const a = point(segment.slice(0, 2)), b = point(segment.slice(2, 4));
    rayDelta.copy(b).sub(a);
    for (const body of mesh.bodies) {
      body.position.copy(a).add(b).multiplyScalar(0.5);
      body.scale.y = rayDelta.length();
      body.quaternion.setFromUnitVectors(beamAxis, rayDelta.clone().normalize());
    }
    mesh.end.position.copy(b); mesh.glow.position.copy(a).add(b).multiplyScalar(0.5);
  }
}

function dimGeometry(factor) {
  if (geometryDim === factor) return;
  geometryDim = factor;
  const materials = new Set();
  modelGroup?.traverse(object => {
    if (object.material) for (const mat of Array.isArray(object.material) ? object.material : [object.material]) materials.add(mat);
  });
  for (const mat of materials) if (mat.color) {
    mat.userData.baseColor ||= mat.color.clone();
    mat.color.copy(mat.userData.baseColor).multiplyScalar(factor);
  }
  portals?.setDim(factor);
}

function disposeGroup(group) {
  if (!group) return;
  const geometries = new Set(), materials = new Set();
  group.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.material) for (const mat of Array.isArray(object.material) ? object.material : [object.material]) materials.add(mat);
  });
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(mat => mat.dispose());
  group.removeFromParent();
}

function send(action, levelId) {
  if (socket?.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify(levelId === undefined ? {action} : {action, level_id: levelId}));
}

function setConnection(text) {
  document.querySelector('#connection-label').textContent = text;
  document.querySelector('.mode').classList.toggle('connected', connected);
}

function applySnapshot(record) {
  snapshot = record; currentLevel = record.level_id || 0;
  const level = data.levels.find(value => value.id === currentLevel);
  const screen = record.screen || 'menu';
  if (screen !== 'menu' && hoverDemo) stopHoverDemo();
  document.querySelector('#menu').hidden = screen !== 'menu';
  document.querySelector('#result').hidden = screen !== 'result';
  document.querySelector('#game-hud').hidden = screen !== 'game';
  document.querySelector('.scene-label').hidden = screen === 'menu';
  const models = modelsForDisplay(record.models || [], level?.models), segments = record.segments || [];
  const success = showSuccess(record, connected);
  const nextGeometryKey = JSON.stringify([currentLevel, models, segments, success]);
  if (!(screen === 'menu' && hoverDemo) && nextGeometryKey !== displayedGeometryKey) {
    updateGeometry(models, segments, currentLevel, success);
    displayedGeometryKey = nextGeometryKey;
  }
  dimGeometry(screen === 'menu' && hoverDemo ? 1 :
    (runningScene(record) || record.preview || record.state === 'LIVE' || screen === 'result' ? 1 : 0.32));
  if (level) {
    document.querySelector('#chamber-number').textContent = String(level.id).padStart(2, '0');
    document.querySelector('#scene-name').textContent = level.name;
    document.querySelector('#level-title').textContent = `第 ${level.id} 关 · ${level.name}`;
  }
  const preview = Boolean(record.preview);
  document.querySelector('#timer').hidden = preview;
  const remaining = Math.max(0, Math.ceil((record.remaining_ms ?? 180000) / 1000));
  document.querySelector('#timer').textContent = `${Math.floor(remaining / 60).toString().padStart(2, '0')}:${(remaining % 60).toString().padStart(2, '0')}`;
  const start = document.querySelector('#start-game');
  start.hidden = preview || record.game_state !== 1;
  start.disabled = !canStart(record, connected);
  document.querySelector('#game-status-text').textContent = record.display_status || '';
  document.querySelector('#skip-game').hidden = preview;
  document.querySelector('#preview-label').hidden = !preview;
  document.querySelector('#preview-label').textContent = level?.playable ? '离线预览' : '展示关卡';
  const notice = document.querySelector('#notice');
  notice.hidden = !record.budget_exceeded;
  notice.textContent = record.budget_exceeded ? `完整光路超过 ${data.maxVisibleSegments} 段显示预算，已保留完整求解结果` : '';
  if (screen === 'result' && record.result) {
    document.querySelector('#result-title').textContent = record.result.outcome;
    document.querySelector('#result-stars').textContent = '★'.repeat(record.result.stars) + '☆'.repeat(3 - record.result.stars);
    document.querySelector('#result-time').textContent = `用时 ${(record.result.elapsed_ms / 1000).toFixed(1)} 秒`;
  }
  viewport.dataset.level = String(currentLevel);
  viewport.dataset.models = String(models.length);
  viewport.dataset.segments = String(segments.length);
  viewport.dataset.termination = String(record.termination ?? '');
  setConnection(record.mode === 'preview' ? '离线预览' : record.mode === 'offline_test' ? '离线测试' : record.connected ? '板端已连接' : '等待板端连接');
}

function returnToMenu() {
  pendingMenu = true;
  errorActive = false;
  document.querySelector('#error').hidden = true;
  // Local navigation remains possible through a backend gap. The request is
  // sent now or on reconnect; only the backend resets the authoritative game.
  if (data && renderer && composer) {
    applySnapshot({screen: 'menu', level_id: 0, models: [], segments: [], ready: false,
      valid: false, connected: false, state: 'MISSING', mode: snapshot?.mode});
  } else {
    document.querySelector('#menu').hidden = false;
    document.querySelector('#game-hud').hidden = true;
    document.querySelector('#result').hidden = true;
  }
  send('menu');
}

function captureHoverFrame(time, force = false) {
  if (!hoverDemo || (!force && time - hoverDemo.lastCaptureAt < HOVER_CAPTURE_INTERVAL_MS)) return;
  const elapsed = Math.max(0, (time - hoverDemo.startedAt) * 0.001);
  const angle = hoverDemo.baseAngle + elapsed * HOVER_ROTATION_SPEED;
  camera.position.set(Math.cos(angle) * hoverDemo.radius, hoverDemo.height,
    Math.sin(angle) * hoverDemo.radius);
  controls.target.copy(HOVER_TARGET);
  camera.lookAt(controls.target);
  portals?.update(renderer, camera, elapsed);
  composer.render();
  // The menu thumbnails are intentionally small. Capturing only while the
  // pointer is over a card keeps the normal game render path untouched.
  hoverDemo.image.src = renderer.domElement.toDataURL('image/jpeg', 0.84);
  hoverDemo.lastCaptureAt = time;
}

function stopHoverDemo() {
  if (!hoverDemo) return;
  const saved = hoverDemo.saved;
  hoverDemo.card.classList.remove('is-demo');
  hoverDemo = null;
  camera.position.copy(saved.position);
  controls.target.copy(saved.target);
  controls.enabled = saved.enabled;
  controls.update();
  updateGeometry([], [], 0);
  resize();
}

function startHoverDemo(level, card, image) {
  if (hoverDemo?.card === card) return;
  stopHoverDemo();
  const horizontalRadius = Math.hypot(camera.position.x, camera.position.z);
  hoverDemo = {
    level,
    card,
    image,
    startedAt: performance.now(),
    lastCaptureAt: -Infinity,
    baseAngle: Math.atan2(camera.position.z, camera.position.x),
    radius: Math.max(12, horizontalRadius),
    height: Math.max(7.5, camera.position.y),
    saved: {position: camera.position.clone(), target: controls.target.clone(), enabled: controls.enabled},
  };
  card.classList.add('is-demo');
  renderer.setSize(MENU_PREVIEW_WIDTH, MENU_PREVIEW_HEIGHT, false);
  composer.setSize(MENU_PREVIEW_WIDTH, MENU_PREVIEW_HEIGHT);
  camera.aspect = MENU_PREVIEW_WIDTH / MENU_PREVIEW_HEIGHT;
  camera.updateProjectionMatrix();
  controls.enabled = false;
  updateGeometry(level.models, [], level.id);
  dimGeometry(1);
  captureHoverFrame(hoverDemo.startedAt, true);
}

function quitProgram() {
  pendingQuit = true; pendingMenu = false;
  clearTimeout(reconnectTimer);
  document.querySelector('#error').hidden = true;
  document.querySelector('#loading').hidden = true;
  document.querySelector('#program-ended').hidden = false;
  if (socket?.readyState === WebSocket.OPEN) send('quit');
  else if (!socket || socket.readyState === WebSocket.CLOSED) connect();
}

function showProgramEnded() {
  pendingQuit = false; disposed = true; connected = false;
  clearTimeout(reconnectTimer); renderer?.setAnimationLoop(null);
  document.querySelector('#error').hidden = true;
  document.querySelector('#program-ended').hidden = false;
  document.querySelector('#program-ended-title').textContent = '程序已结束';
  document.querySelector('#program-ended-message').textContent = '电脑后台已关闭，可以关闭此页面。';
}

document.querySelector('#error-menu').addEventListener('click', returnToMenu);
document.querySelector('#error-reload').addEventListener('click', () => window.location.reload());
document.querySelectorAll('[data-action="quit"]').forEach(button => button.addEventListener('click', quitProgram));

function connect() {
  const next = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
  socket = next;
  next.onopen = () => {
    connected = true; lastPacket = performance.now();
    if (pendingQuit) send('quit');
    else if (pendingMenu) send('menu');
  };
  next.onmessage = event => {
    if (next !== socket) return;
    try {
      const record = JSON.parse(event.data); lastPacket = performance.now();
      if (record.screen === 'closed') { showProgramEnded(); return; }
      if (pendingQuit) return;
      if (pendingMenu && record.screen !== 'menu') return;
      if (errorActive && record.screen !== 'menu') { snapshot = record; return; }
      applySnapshot(record);
      if (record.screen === 'menu') {
        pendingMenu = false; errorActive = false;
        document.querySelector('#error').hidden = true;
      }
    } catch (error) { showError(error); }
  };
  next.onclose = event => {
    if (disposed || next !== socket) return;
    connected = false;
    document.querySelector('#start-game').disabled = true;
    if (!errorActive && snapshot && !snapshot.preview && snapshot.screen !== 'result') {
      applySnapshot(backendGap(snapshot));
    }
    setConnection(event.code === 4001 ? '另一页面已接管' : '后端连接断开');
    if (event.code !== 4001) reconnectTimer = setTimeout(connect, 1000);
  };
}

async function buildMenu() {
  const menu = document.querySelector('#level-grid');
  const oldAspect = camera.aspect;
  renderer.setSize(MENU_PREVIEW_WIDTH, MENU_PREVIEW_HEIGHT, false);
  composer.setSize(MENU_PREVIEW_WIDTH, MENU_PREVIEW_HEIGHT);
  camera.aspect = 16 / 9; camera.updateProjectionMatrix();
  for (const level of data.levels) {
    const card = document.createElement('button'); card.className = 'level-card';
    card.setAttribute('aria-label', `第 ${level.id} 关 ${level.name}`);
    const image = document.createElement('img'); image.alt = `${level.name}三维布局`;
    updateGeometry(level.models, [], level.id); dimGeometry(1);
    portals?.update(renderer, camera, 0); composer.render();
    image.src = renderer.domElement.toDataURL('image/png');
    const footer = document.createElement('div'); footer.className = 'card-caption';
    const title = document.createElement('span'); title.textContent = `${String(level.id).padStart(2, '0')}  ${level.name}`;
    const indicator = document.createElement('span'); indicator.className = 'demo-indicator'; indicator.textContent = '自动演示';
    footer.append(title, indicator); card.append(image, footer);
    card.addEventListener('mouseenter', () => startHoverDemo(level, card, image));
    card.addEventListener('mouseleave', stopHoverDemo);
    card.addEventListener('focus', () => startHoverDemo(level, card, image));
    card.addEventListener('blur', stopHoverDemo);
    card.addEventListener('click', () => { stopHoverDemo(); send('select', level.id); }); menu.append(card);
    if (level.id % 3 === 0) await new Promise(requestAnimationFrame);
  }
  camera.aspect = oldAspect; camera.updateProjectionMatrix();
  updateGeometry([], [], 0); resize();
}

function resize() {
  const width = viewport.clientWidth, height = viewport.clientHeight;
  renderer.setSize(width, height);
  composer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function showError(error) {
  document.querySelector('#loading').hidden = true;
  document.querySelector('#error').hidden = false;
  document.querySelector('#error-message').textContent = error?.message || String(error);
  if (!errorActive) console.error(error);
  errorActive = true;
}

async function init() {
  const response = await fetch('/api/catalog', {cache: 'no-store'});
  if (!response.ok) throw new Error(`场景数据加载失败（HTTP ${response.status}）。请从本地 HTTP 地址打开页面。`);
  data = await response.json();
  if (data.levels.length !== 15) throw new Error('关卡目录不完整，需要参考版的15个关卡。');
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  viewport.appendChild(renderer.domElement);
  camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(9.2, 9.1, 12.5);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.3, -0.2); controls.enableDamping = true; controls.dampingFactor = 0.07;
  controls.enablePan = false; controls.minDistance = 7; controls.maxDistance = 30;
  controls.minPolarAngle = Math.PI / 7; controls.maxPolarAngle = Math.PI / 2.25;
  controls.update();
  const environmentScene = new RoomEnvironment();
  const environmentGenerator = new THREE.PMREMGenerator(renderer);
  const environmentTarget = environmentGenerator.fromScene(environmentScene, 0.04);
  scene.environment = environmentTarget.texture;
  scene.environmentIntensity = 0.35;
  staticResources.add(environmentTarget);
  environmentScene.dispose(); environmentGenerator.dispose();
  buildRoom();
  composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), 0.35, 0.4, 1.05));
  composer.addPass(new OutputPass());
  await buildMenu();
  if (disposed || pendingQuit) return;
  document.querySelectorAll('[data-action]:not([data-action="quit"])').forEach(button => button.addEventListener('click', () => send(button.dataset.action)));
  connect();
  window.addEventListener('resize', resize);
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault(); renderer.setAnimationLoop(null);
    showError(new Error('图形上下文已丢失，请刷新页面重新加载。'));
  });
  resize();
  document.querySelector('#loading').hidden = true;
  renderer.setAnimationLoop(time => {
    if (disposed || document.hidden || errorActive || pendingQuit) return;
    try {
      const seconds = time * 0.001;
      for (const halo of beamMaterials) halo.opacity = 0.1 + Math.sin(seconds * 2.3) * 0.015;
      if (hoverDemo) {
        captureHoverFrame(time);
      } else {
        controls.update();
        if (connected && snapshot && !snapshot.preview && snapshot.screen === 'game' &&
            snapshot.state !== 'DISCONNECTED' &&
            performance.now() - lastPacket > (snapshot.scene_max_age_ms ?? data.sceneMaxAgeMs)) {
          // Keep the entire running scene with its original stamps through gaps.
          // Only the backend can accept new geometry or award a result.
          applySnapshot(backendGap(snapshot));
          setConnection('等待后端更新');
        }
        portals?.update(renderer, camera, seconds);
        composer.render();
      }
      renderedFrames++;
    } catch (error) { showError(error); }
  });
  // Read-only diagnostic hook for geometry/viewport/resource QA; no controls or solver.
  window.rayPreview = {
    inspect: () => ({ level: currentLevel, width: data.width, height: data.height, snapshot, connected,
      modelPoses: [...modelsByType.values()].map(mesh => ({type: mesh.name, position: mesh.position.toArray(), angle: mesh.rotation.y})),
      portalPoses: portals?.inspect() ?? [],
      beams: rayMeshes.filter(mesh => mesh.group.visible).map(mesh => {
        const body = mesh.bodies[0], delta = new THREE.Vector3(0, 1, 0).applyQuaternion(body.quaternion).multiplyScalar(body.scale.y / 2);
        return {start: body.position.clone().sub(delta).toArray(), end: body.position.clone().add(delta).toArray()};
      }),
      camera: camera.position.toArray(), target: controls.target.toArray(), memory: { ...renderer.info.memory }, frame: renderedFrames,
      canvas: { width: renderer.domElement.width, height: renderer.domElement.height } }),
  };
  window.addEventListener('pagehide', () => {
    disposed = true; clearTimeout(reconnectTimer); socket?.close(); renderer.setAnimationLoop(null); controls.dispose(); portals?.dispose();
    disposeGroup(modelGroup); disposeGroup(scene); staticResources.forEach(resource => resource.dispose());
    composer.passes.forEach(pass => pass.dispose?.()); composer.dispose(); renderer.dispose();
  }, { once: true });
}

init().catch(showError);
