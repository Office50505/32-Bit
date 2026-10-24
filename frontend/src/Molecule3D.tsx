import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { DEMO_GEOMETRY } from "./demoData";
import type { ViewerStyle } from "./domain";

interface Props {
  moleculeId: string;
  style: ViewerStyle;
  autorotate: boolean;
  highlightedAtom?: number;
  onIssueClick: () => void;
  resetSignal: number;
  zoomSignal: number;
}

export default function Molecule3D({ moleculeId, style, autorotate, highlightedAtom, onIssueClick, resetSignal, zoomSignal }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  useEffect(() => {
    const camera = cameraRef.current;
    if (camera && zoomSignal) {
      camera.position.multiplyScalar(zoomSignal > 0 ? 0.85 : 1.17);
      camera.updateProjectionMatrix();
    }
  }, [zoomSignal]);

  useEffect(() => {
    if (resetSignal && controlsRef.current && cameraRef.current) {
      cameraRef.current.position.set(0, 0, 11);
      controlsRef.current.target.set(0, 0, 0);
      controlsRef.current.update();
    }
  }, [resetSignal]);

  useEffect(() => {
    const host = mount.current;
    const geometry = DEMO_GEOMETRY[moleculeId];
    if (!host || !geometry) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#fbfcfd");
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 11);
    cameraRef.current = camera;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      host.textContent = "3D view is unavailable on this device. Use the 2D view.";
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.minDistance = 4;
    controls.maxDistance = 23;
    controlsRef.current = controls;
    scene.add(new THREE.AmbientLight("#ffffff", 2));
    const light = new THREE.DirectionalLight("#ffffff", 2.5);
    light.position.set(4, 7, 9);
    scene.add(light);
    const root = new THREE.Group();
    scene.add(root);
    const colors = { C: "#405469", O: "#e11d48", H: "#d9e1e8" };
    const radius = style === "space-filling" ? 0.48 : style === "stick" ? 0.2 : 0.32;
    const atomMeshes: THREE.Mesh[] = [];
    geometry.atoms.forEach((atom) => {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 24, 16),
        new THREE.MeshStandardMaterial({ color: colors[atom.element], roughness: 0.36, metalness: 0.06 }),
      );
      mesh.position.set(...atom.position);
      root.add(mesh);
      atomMeshes.push(mesh);
    });
    if (style !== "space-filling") {
      geometry.bonds.forEach((bond) => {
        const start = new THREE.Vector3(...geometry.atoms[bond.from].position);
        const end = new THREE.Vector3(...geometry.atoms[bond.to].position);
        const direction = new THREE.Vector3().subVectors(end, start);
        const mesh = new THREE.Mesh(
          new THREE.CylinderGeometry(style === "stick" ? 0.12 : 0.075, style === "stick" ? 0.12 : 0.075, direction.length(), 12),
          new THREE.MeshStandardMaterial({ color: "#9aa9b8", roughness: 0.4 }),
        );
        mesh.position.copy(start).add(end).multiplyScalar(0.5);
        mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
        root.add(mesh);
      });
    }
    let halo: THREE.Mesh | null = null;
    if (highlightedAtom !== undefined && atomMeshes[highlightedAtom]) {
      halo = new THREE.Mesh(
        new THREE.SphereGeometry(radius + 0.32, 28, 20),
        new THREE.MeshBasicMaterial({ color: "#e11d48", transparent: true, opacity: 0.22, side: THREE.DoubleSide }),
      );
      halo.position.copy(atomMeshes[highlightedAtom].position);
      root.add(halo);
    }
    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const click = (event: MouseEvent) => {
      if (highlightedAtom === undefined) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      if (raycaster.intersectObjects([atomMeshes[highlightedAtom], ...(halo ? [halo] : [])]).length) onIssueClick();
    };
    renderer.domElement.addEventListener("click", click);
    let frame = 0;
    const animate = (time: number) => {
      frame = requestAnimationFrame(animate);
      controls.autoRotate = autorotate;
      controls.autoRotateSpeed = 1.2;
      controls.update();
      if (halo) halo.scale.setScalar(1 + Math.sin(time / 280) * 0.09);
      renderer.render(scene, camera);
    };
    frame = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener("click", click);
      controls.dispose();
      root.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material;
          if (Array.isArray(material)) material.forEach((item) => item.dispose());
          else material.dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      controlsRef.current = null;
      cameraRef.current = null;
    };
  }, [moleculeId, style, autorotate, highlightedAtom, onIssueClick]);

  return <div ref={mount} className="molecule-3d" aria-label="Interactive illustrative 3D molecular view" />;
}
