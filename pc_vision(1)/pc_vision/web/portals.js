import * as THREE from 'three';

const up = new THREE.Vector3(0, 1, 0);
const bias = new THREE.Matrix4().set(
  0.5, 0, 0, 0.5,
  0, 0.5, 0, 0.5,
  0, 0, 0.5, 0.5,
  0, 0, 0, 1,
);

const windowVertex = `
  uniform mat4 textureMatrix;
  varying vec4 projected;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    projected = textureMatrix * world;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;
const windowFragment = `
  uniform sampler2D portalTexture;
  uniform float dimming;
  varying vec4 projected;
  void main() {
    vec2 uv = projected.xy / projected.w;
    gl_FragColor = texture2D(portalTexture, clamp(uv, 0.0, 1.0));
    gl_FragColor.rgb *= dimming;
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;
const rimVertex = `
  varying vec2 ringPosition;
  #include <clipping_planes_pars_vertex>
  void main() {
    ringPosition = position.xy;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }
`;
const rimFragment = `
  uniform vec3 color;
  uniform float time;
  varying vec2 ringPosition;
  #include <clipping_planes_pars_fragment>
  void main() {
    #include <clipping_planes_fragment>
    float r = length(ringPosition);
    float a = atan(ringPosition.y, ringPosition.x);
    float flicker = sin(a * 19.0 - time * 3.2)
                  * sin(a * 37.0 + time * 5.1);
    float filament = 1.025 + 0.007 * flicker;
    float core = exp(-abs(r - filament) * 210.0);
    float second = exp(-abs(r - 1.067 - flicker * 0.013) * 160.0);
    float halo = exp(-abs(r - 1.035) * 24.0);
    float alpha = (core + second * 0.32 + halo * 0.38)
                * smoothstep(1.0, 1.008, r);
    gl_FragColor = vec4(color * (1.8 + core * 4.0), alpha);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

/** C ray_game portal windows, in the same horizontal plane as its rays. */
export function createPortalPair(scene, objects, {
  width, height, scale = 0.01, beamHeight = 1.15,
}) {
  const group = new THREE.Group();
  group.name = 'paired-portals';
  scene.add(group);
  const portals = [];
  const ownedGeometries = new Set();
  const ownedMaterials = new Set();
  const ownGeometry = geometry => (ownedGeometries.add(geometry), geometry);
  const ownMaterial = material => (ownedMaterials.add(material), material);
  const viewport = new THREE.Vector4();
  const scissor = new THREE.Vector4();
  const drawingSize = new THREE.Vector2();
  const eye = new THREE.Vector3();
  const sourcePoint = new THREE.Vector3();
  const destinationPoint = new THREE.Vector3();
  const translation = new THREE.Vector3();
  const transformedView = new THREE.Matrix4();

  for (const object of objects.filter(o => o.type === 'PORTAL_A' || o.type === 'PORTAL_B')) {
    const u = new THREE.Vector3(object.axis[0], 0, object.axis[1]).normalize();
    const n = new THREE.Vector3(-u.z, 0, u.x);
    const center = new THREE.Vector3(
      (object.center[0] - width / 2) * scale,
      beamHeight,
      (object.center[1] - height / 2) * scale,
    );
    const frame = new THREE.Matrix4().makeBasis(u, up, n);
    const holder = new THREE.Group();
    holder.name = object.type;
    holder.position.copy(center);
    holder.quaternion.setFromRotationMatrix(frame);
    group.add(holder);
    const color = new THREE.Color(object.type === 'PORTAL_A' ? 0x008dff : 0xff6509);
    const radiusX = object.size[0] * scale / 2;
    const radiusY = beamHeight - 0.07;
    const halfDepth = object.size[1] * scale / 2;
    const target = new THREE.WebGLRenderTarget(1, 1, {
      type: THREE.HalfFloatType,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      depthBuffer: true,
    });
    target.texture.name = `${object.type}-view`;
    target.texture.colorSpace = THREE.LinearSRGBColorSpace;
    const surfaceMaterial = ownMaterial(new THREE.ShaderMaterial({
      uniforms: {
        portalTexture: {value: target.texture},
        dimming: {value: 1},
        textureMatrix: {value: new THREE.Matrix4()},
      },
      vertexShader: windowVertex,
      fragmentShader: windowFragment,
      side: THREE.DoubleSide,
    }));
    const rimMaterial = ownMaterial(new THREE.ShaderMaterial({
      uniforms: {color: {value: color}, time: {value: 0}},
      vertexShader: rimVertex,
      fragmentShader: rimFragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      clipping: true,
    }));
    const windowGeometry = ownGeometry(new THREE.CircleGeometry(1, 96));
    // The luminous frame starts outside the entire legal horizontal aperture.
    const rimGeometry = ownGeometry(new THREE.RingGeometry(1, 1.28, 128, 2));
    const surfaces = [];
    for (const side of [-1, 1]) {
      const surface = new THREE.Mesh(windowGeometry, surfaceMaterial);
      surface.position.z = side * halfDepth;
      surface.scale.set(radiusX, radiusY, 1);
      surface.name = `${object.type}-window-${side}`;
      holder.add(surface);
      const rim = new THREE.Mesh(rimGeometry, rimMaterial);
      rim.position.z = side * (halfDepth + 0.008);
      rim.scale.set(radiusX, radiusY, 1);
      holder.add(rim);
      surfaces.push({side, mesh: surface, rim});
    }
    const footMaterial = ownMaterial(new THREE.MeshStandardMaterial({
      color: 0x252b32, roughness: 0.46, metalness: 0.7,
    }));
    const footGeometry = ownGeometry(new THREE.BoxGeometry(0.24, 0.12, halfDepth * 2 + 0.18));
    for (const side of [-1, 1]) {
      const foot = new THREE.Mesh(footGeometry, footMaterial);
      foot.position.set(side * (radiusX + 0.14), -beamHeight + 0.06, 0);
      foot.castShadow = true;
      foot.receiveShadow = true;
      holder.add(foot);
    }
    const light = new THREE.PointLight(color, 3.4, 3.8, 2);
    light.position.y = -0.48;
    holder.add(light);
    portals.push({
      type: object.type, holder, light, color: color.clone(),
      u, n, center, frame, halfDepth, surfaces, target, surfaceMaterial, rimMaterial,
      camera: new THREE.PerspectiveCamera(),
      transform: new THREE.Matrix4(),
      clip: new THREE.Plane(),
      selectedSide: 1,
    });
  }

  function update(renderer, camera, timeSeconds) {
    if (portals.length !== 2) return;
    camera.updateMatrixWorld();
    camera.getWorldPosition(eye);
    renderer.getDrawingBufferSize(drawingSize);
    const factor = Math.min(1, 1280 / drawingSize.x, 900 / drawingSize.y);
    const targetWidth = Math.max(1, Math.round(drawingSize.x * factor));
    const targetHeight = Math.max(1, Math.round(drawingSize.y * factor));
    const savedTarget = renderer.getRenderTarget();
    const savedCubeFace = renderer.getActiveCubeFace();
    const savedMipLevel = renderer.getActiveMipmapLevel();
    const savedPlanes = renderer.clippingPlanes;
    const savedShadowAutoUpdate = renderer.shadowMap.autoUpdate;
    const savedXrEnabled = renderer.xr.enabled;
    const savedScissorTest = renderer.getScissorTest();
    renderer.getViewport(viewport);
    renderer.getScissor(scissor);
    renderer.xr.enabled = false;
    renderer.shadowMap.autoUpdate = false;
    renderer.setScissorTest(false);

    for (const portal of portals) {
      portal.selectedSide = eye.clone().sub(portal.center).dot(portal.n) >= 0 ? 1 : -1;
      portal.rimMaterial.uniforms.time.value = timeSeconds;
      for (const surface of portal.surfaces) {
        surface.mesh.visible = false;
        surface.rim.visible = false;
      }
    }
    try {
      for (let index = 0; index < portals.length; index++) {
        const source = portals[index];
        const destination = portals[1 - index];
        const side = source.selectedSide;
        sourcePoint.copy(source.center).addScaledVector(source.n, side * source.halfDepth);
        destinationPoint.copy(destination.center).addScaledVector(destination.n, -side * destination.halfDepth);
        // The C core preserves local tangent/normal components; no extra half turn.
        source.transform.copy(source.frame).invert().premultiply(destination.frame);
        translation.copy(sourcePoint).applyMatrix4(source.transform);
        translation.subVectors(destinationPoint, translation);
        source.transform.setPosition(translation);
        transformedView.multiplyMatrices(source.transform, camera.matrixWorld);
        transformedView.decompose(source.camera.position, source.camera.quaternion, source.camera.scale);
        source.camera.projectionMatrix.copy(camera.projectionMatrix);
        source.camera.projectionMatrixInverse.copy(camera.projectionMatrixInverse);
        source.camera.near = camera.near;
        source.camera.far = camera.far;
        source.camera.layers.mask = camera.layers.mask;
        source.camera.updateMatrixWorld(true);
        source.surfaceMaterial.uniforms.textureMatrix.value.copy(bias)
          .multiply(source.camera.projectionMatrix)
          .multiply(source.camera.matrixWorldInverse)
          .multiply(source.transform);
        // Keep only the exterior half-space beyond the paired exit surface.
        source.clip.setFromNormalAndCoplanarPoint(
          destination.n.clone().multiplyScalar(-side), destinationPoint,
        );
        renderer.clippingPlanes = [...savedPlanes, source.clip];
        if (source.target.width !== targetWidth || source.target.height !== targetHeight) {
          source.target.setSize(targetWidth, targetHeight);
        }
        renderer.setRenderTarget(source.target);
        renderer.setViewport(0, 0, targetWidth, targetHeight);
        renderer.clear();
        renderer.render(scene, source.camera);
      }
    } finally {
      for (const portal of portals) {
        for (const surface of portal.surfaces) {
          surface.mesh.visible = surface.side === portal.selectedSide;
          surface.rim.visible = surface.mesh.visible;
        }
      }
      renderer.clippingPlanes = savedPlanes;
      renderer.shadowMap.autoUpdate = savedShadowAutoUpdate;
      renderer.xr.enabled = savedXrEnabled;
      renderer.setRenderTarget(savedTarget, savedCubeFace, savedMipLevel);
      renderer.setViewport(viewport);
      renderer.setScissor(scissor);
      renderer.setScissorTest(savedScissorTest);
    }
  }

  function dispose() {
    group.removeFromParent();
    for (const portal of portals) portal.target.dispose();
    for (const geometry of ownedGeometries) geometry.dispose();
    for (const material of ownedMaterials) material.dispose();
  }

  function setModels(objects) {
    for (const portal of portals) {
      const object = objects.find(value => value.type === portal.type);
      if (!object) continue;
      portal.u.set(object.axis[0], 0, object.axis[1]).normalize();
      portal.n.set(-portal.u.z, 0, portal.u.x);
      portal.center.set((object.center[0] - width / 2) * scale, beamHeight,
        (object.center[1] - height / 2) * scale);
      portal.frame.makeBasis(portal.u, up, portal.n);
      portal.holder.position.copy(portal.center);
      portal.holder.quaternion.setFromRotationMatrix(portal.frame);
    }
  }

  function setDim(factor) {
    for (const portal of portals) {
      portal.rimMaterial.uniforms.color.value.copy(portal.color).multiplyScalar(factor);
      portal.surfaceMaterial.uniforms.dimming.value = factor;
      portal.light.intensity = 3.4 * factor;
    }
  }

  return {group, update, dispose, setModels, setDim,
    inspect: () => portals.map(portal => ({type: portal.type, center: portal.center.toArray(), axis: portal.u.toArray()})),
  };
}
