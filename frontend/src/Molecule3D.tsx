import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { DEMO_GEOMETRY } from "./demoData";
import type { ViewerStyle } from "./domain";

interface Props {
  moleculeId: string;
  style: ViewerStyle;
  autorotate: boolean;
  highlightedAtom?: number;
  resetSignal: number;
  zoom: number;
}

export default function Molecule3D({ moleculeId, style, autorotate, highlightedAtom, resetSignal, zoom }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const callout = useRef<HTMLButtonElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null);
  const fittedViewRef = useRef<{ position: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const invalidateRef = useRef<(() => void) | null>(null);
  const autorotateRef = useRef(autorotate);
  const zoomRef = useRef(zoom);
  const [calloutOpen, setCalloutOpen] = useState(true);

  useEffect(() => { autorotateRef.current = autorotate; }, [autorotate]);
  useEffect(() => {
    const camera = cameraRef.current;
    zoomRef.current = zoom;
    if (camera) {
      camera.zoom = zoom;
      camera.updateProjectionMatrix();
      invalidateRef.current?.();
    }
  }, [zoom]);
  useEffect(() => {
    if (resetSignal && controlsRef.current && cameraRef.current && fittedViewRef.current) {
      cameraRef.current.position.copy(fittedViewRef.current.position);
      controlsRef.current.target.copy(fittedViewRef.current.target);
      controlsRef.current.update();
      invalidateRef.current?.();
    }
  }, [resetSignal]);

  useEffect(() => {
    const host = mount.current;
    const geometry = DEMO_GEOMETRY[moleculeId];
    if (!host || !geometry) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0f172a");
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
    camera.zoom = zoomRef.current;
    cameraRef.current = camera;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false }); }
    catch { host.dataset.webglUnavailable = "true"; return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controlsRef.current = controls;

    scene.add(new THREE.AmbientLight("#dbeafe", 2.2));
    const light = new THREE.DirectionalLight("#ffffff", 3.2);
    light.position.set(3, 6, 7);
    scene.add(light);
    const rim = new THREE.DirectionalLight("#22d3ee", 1);
    rim.position.set(-5, 1, -4);
    scene.add(rim);
    const grid = new THREE.GridHelper(30, 30, "#1d4863", "#17334b");
    grid.position.y = -2.2;
    scene.add(grid);

    const model = new THREE.Group();
    scene.add(model);
    const radius = style === "space-filling" ? 0.49 : style === "wireframe" ? 0.28 : 0.31;
    const atomMeshes: THREE.Mesh[] = [];
    geometry.atoms.forEach((atom, index) => {
      const isProblemAtom = index === highlightedAtom;
      const material = isProblemAtom
        ? new THREE.MeshStandardMaterial({ color: "#ef234b", emissive: "#8f1530", emissiveIntensity: 0.45, roughness: 0.36 })
        : style === "wireframe"
          ? new THREE.MeshBasicMaterial({ color: atom.element === "O" ? "#fb7185" : "#b9d1e0", wireframe: true })
          : new THREE.MeshStandardMaterial({ color: atom.element === "O" ? "#f43f5e" : atom.element === "H" ? "#f8fafc" : "#a8b8c8", roughness: 0.32, metalness: 0.08 });
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(isProblemAtom ? radius * 1.18 : radius, 32, 24), material);
      mesh.position.set(...atom.position);
      model.add(mesh);
      atomMeshes.push(mesh);
    });
    if (style !== "space-filling") geometry.bonds.forEach((bond) => {
      const from = new THREE.Vector3(...geometry.atoms[bond.from].position);
      const to = new THREE.Vector3(...geometry.atoms[bond.to].position);
      const direction = new THREE.Vector3().subVectors(to, from);
      const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(style === "wireframe" ? 0.025 : 0.075, style === "wireframe" ? 0.025 : 0.075, direction.length(), 12),
        new THREE.MeshStandardMaterial({ color: style === "wireframe" ? "#57a7b6" : "#cbd5e1", roughness: 0.4 }),
      );
      mesh.position.copy(from).add(to).multiplyScalar(0.5);
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
      model.add(mesh);
    });

    const targetAtom = highlightedAtom === undefined ? undefined : atomMeshes[highlightedAtom];
    const bounds = new THREE.Box3();
    geometry.atoms.forEach((atom) => bounds.expandByPoint(new THREE.Vector3(...atom.position)));
    bounds.expandByScalar(radius * 1.18);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    model.position.copy(center).multiplyScalar(-1);
    let needsRender = true;
    const markDirty = () => { needsRender = true; };
    invalidateRef.current = markDirty;
    controls.addEventListener("change", markDirty);

    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      const pixelRatio = Math.min(window.devicePixelRatio, 2);
      if (renderer.getPixelRatio() !== pixelRatio) renderer.setPixelRatio(pixelRatio);
      const aspect = width / height;
      const viewHeight = Math.max(4, size.y * 1.5, size.x / aspect * 1.35);
      const viewWidth = viewHeight * aspect;
      camera.left = -viewWidth / 2;
      camera.right = viewWidth / 2;
      camera.top = viewHeight / 2;
      camera.bottom = -viewHeight / 2;
      const target = new THREE.Vector3();
      const position = new THREE.Vector3(0, viewHeight * 0.12, Math.max(12, size.x * 2));
      camera.position.copy(position);
      controls.target.copy(target);
      controls.minZoom = 0.65;
      controls.maxZoom = 1.55;
      camera.zoom = zoomRef.current;
      camera.updateProjectionMatrix();
      controls.update();
      fittedViewRef.current = { position, target };
      renderer.setSize(width, height, false);
      needsRender = true;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const onCanvasClick = (event: MouseEvent) => {
      if (!targetAtom) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set((event.clientX - bounds.left) / bounds.width * 2 - 1, -((event.clientY - bounds.top) / bounds.height * 2 - 1));
      raycaster.setFromCamera(pointer, camera);
      if (raycaster.intersectObject(targetAtom).length) {
        setCalloutOpen(true);
        needsRender = true;
      }
    };
    renderer.domElement.addEventListener("click", onCanvasClick);

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.autoRotate = autorotateRef.current;
      controls.autoRotateSpeed = 1;
      controls.update();
      if (!needsRender) return;
      if (targetAtom && callout.current) {
        const point = targetAtom.getWorldPosition(new THREE.Vector3()).project(camera);
        const atomX = (point.x + 1) * host.clientWidth / 2;
        const halfWidth = callout.current.offsetWidth / 2;
        const centerX = Math.max(halfWidth + 8, Math.min(host.clientWidth - halfWidth - 8, atomX));
        callout.current.style.left = `${centerX}px`;
        callout.current.style.top = `${Math.max(48, (-point.y + 1) * host.clientHeight / 2 - 29)}px`;
        callout.current.style.setProperty("--arrow-offset", `${Math.max(-halfWidth + 12, Math.min(halfWidth - 12, atomX - centerX))}px`);
      }
      renderer.render(scene, camera);
      needsRender = false;
    };
    frame = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener("click", onCanvasClick);
      controls.removeEventListener("change", markDirty);
      controls.dispose();
      model.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((item) => item.dispose());
          else material.dispose();
        }
      });
      grid.geometry.dispose();
      if (Array.isArray(grid.material)) grid.material.forEach((item) => item.dispose());
      else grid.material.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      controlsRef.current = null;
      cameraRef.current = null;
      fittedViewRef.current = null;
      invalidateRef.current = null;
    };
  }, [moleculeId, style, highlightedAtom]);

  return <div ref={mount} className="molecule-3d" aria-label="Interactive illustrative 3D molecular view">
    {highlightedAtom !== undefined && calloutOpen && <button ref={callout} className="atom-callout" onClick={() => setCalloutOpen(false)} title="Click to hide; click the highlighted atom to show again">
      Oxygen atom {highlightedAtom + 1}: impossible valence
    </button>}
    <span className="webgl-fallback">3D view is unavailable on this device. Use the 2D view.</span>
  </div>;
}
