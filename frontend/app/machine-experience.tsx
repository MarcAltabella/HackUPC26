"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { ContactShadows, Edges, Environment, Grid, Html, OrbitControls, RoundedBox, useTexture } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import hpLogoImage from "../data/HP_logo_2025.svg.png";

export const HP_METAL_JET_S100_DIMENSIONS = {
  widthMm: 2975,
  depthMm: 1350,
  heightMm: 2410,
  weightKg: 851,
};

type Vector3Tuple = [number, number, number];

// ── Blueprint context ─────────────────────────────────────────────────────────

const BlueprintCtx = createContext(false);

// ── Component status types ────────────────────────────────────────────────────

export type CompStatus = "FUNCTIONAL" | "NOMINAL" | "WARNING" | "DEGRADED" | "CRITICAL" | "FAILED";

export interface ComponentStatuses {
  blade:      CompStatus;
  motor:      CompStatus;
  rail:       CompStatus;
  nozzle:     CompStatus;
  resistors:  CompStatus;
  cleaning:   CompStatus;
  heater:     CompStatus;
  sensor:     CompStatus;
  insulation: CompStatus;
}

type DotKey = keyof ComponentStatuses;
type DotClickHandler = (key: DotKey) => void;

function statusDotColor(s: CompStatus): string {
  if (s === "FAILED"   || s === "CRITICAL") return "#f87171";
  if (s === "DEGRADED")                      return "#fb923c";
  if (s === "WARNING")                       return "#fde047";
  return "#4ade80";
}

function statusVisible(s: CompStatus): boolean {
  return s !== "FUNCTIONAL" && s !== "NOMINAL";
}

function statusNeedsRedHighlight(s: CompStatus): boolean {
  return s === "WARNING" || s === "DEGRADED" || s === "CRITICAL" || s === "FAILED";
}

// ── Component hotspot positions (model-local, inside [0,0.09,0] group) ───────

const HOTSPOTS: Record<DotKey, Vector3Tuple> = {
  blade:      [ 0.14, 1.24,  0.54],
  motor:      [-0.55, 1.20,  0.33],
  rail:       [ 0.88, 1.17,  0.38],
  nozzle:     [ 0.14, 1.44,  0.27],
  resistors:  [ 0.55, 1.49,  0.16],
  cleaning:   [-0.20, 1.38,  0.54],
  heater:     [ 1.26, 0.73,  0.05],
  sensor:     [ 0.85, 0.88, -0.15],
  insulation: [ 1.48, 0.52,  0.10],
};

const DOT_LABELS: Record<DotKey, { title: string; group: string }> = {
  blade: { title: "Blade", group: "Recoating" },
  motor: { title: "Motor", group: "Recoating" },
  rail: { title: "Rail", group: "Recoating" },
  nozzle: { title: "Nozzle", group: "Printhead" },
  resistors: { title: "Resistors", group: "Printhead" },
  cleaning: { title: "Cleaning", group: "Printhead" },
  heater: { title: "Heater", group: "Thermal" },
  sensor: { title: "Sensor", group: "Thermal" },
  insulation: { title: "Insulation", group: "Thermal" },
};

// Transform hotspot from model-local → world space
// Outer group: position=[0,-0.78,0], rotation=[0,-0.42,0]
// Inner model group: position=[0,0.09,0]
function hotspotWorldPos(key: DotKey): THREE.Vector3 {
  const [hx, hy, hz] = HOTSPOTS[key];
  const v = new THREE.Vector3(hx, hy + 0.09, hz);
  v.applyEuler(new THREE.Euler(0, -0.42, 0));
  v.y -= 0.78;
  return v;
}

// ── Camera focuser — lerps OrbitControls target toward focusWorld ─────────────

function CameraFocuser({ focusWorld }: { focusWorld: THREE.Vector3 | null }) {
  const controls  = useThree(s => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | undefined;
  const targetRef = useRef<THREE.Vector3 | null>(null);

  useEffect(() => {
    targetRef.current = focusWorld ? focusWorld.clone() : null;
  }, [focusWorld]);

  useFrame(() => {
    if (!targetRef.current || !controls) return;
    if (controls.target.distanceTo(targetRef.current) < 0.003) return;
    controls.target.lerp(targetRef.current, 0.09);
    controls.update();
  });

  return null;
}

// ── Alert dot mesh ────────────────────────────────────────────────────────────

function AlertDot({
  position,
  status,
  dotKey,
  onDotClick,
}: {
  position: Vector3Tuple;
  status: CompStatus;
  dotKey: DotKey;
  onDotClick?: DotClickHandler;
}) {
  const bp = useContext(BlueprintCtx);
  const coreRef = useRef<THREE.Mesh>(null!);
  const alertAreaRef = useRef<THREE.Mesh>(null!);
  const [isHovered, setIsHovered] = useState(false);
  const visible = statusVisible(status);
  const redHighlight = statusNeedsRedHighlight(status);
  const isCrit  = status === "CRITICAL" || status === "FAILED";
  const color   = statusDotColor(status);
  const speed   = isCrit ? 5.5 : 2.5;
  const amp     = isCrit ? 0.45 : 0.18;
  const label   = DOT_LABELS[dotKey];

  useFrame(({ clock }) => {
    if (!coreRef.current || !visible) return;
    const t = clock.getElapsedTime();
    coreRef.current.scale.setScalar(1 + amp * Math.abs(Math.sin(t * speed)));
  });

  useFrame(({ clock }) => {
    if (!alertAreaRef.current || !bp || !redHighlight) return;
    const t = clock.getElapsedTime();
    const pulse = 0.14 + Math.abs(Math.sin(t * 2.1)) * 0.18;
    (alertAreaRef.current.material as THREE.MeshStandardMaterial).opacity = pulse;
  });

  function handleClick(e: { stopPropagation: () => void }) {
    e.stopPropagation();
    onDotClick?.(dotKey);
  }

  function handlePointerOver(e: { stopPropagation: () => void }) {
    e.stopPropagation();
    setIsHovered(true);
    document.body.style.cursor = "pointer";
  }

  function handlePointerOut() {
    setIsHovered(false);
    document.body.style.cursor = "auto";
  }

  return (
    <group position={position}>
      {/* Hover/click hit area is always present so labels are discoverable */}
      <mesh onClick={handleClick} onPointerOver={handlePointerOver} onPointerOut={handlePointerOut}>
        <sphereGeometry args={[0.095, 14, 14]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>

      {visible && (
        <>
          {/* Blueprint red component-area highlight */}
          {bp && redHighlight && (
            <mesh ref={alertAreaRef}>
              <sphereGeometry args={[0.13, 18, 18]} />
              <meshStandardMaterial
                color="#ff4d4f"
                emissive="#ff4d4f"
                emissiveIntensity={0.35}
                transparent
                opacity={0.2}
                depthWrite={false}
              />
            </mesh>
          )}

          {/* Clickable core (pulsing) */}
          <mesh
            ref={coreRef}
            onClick={handleClick}
            onPointerOver={handlePointerOver}
            onPointerOut={handlePointerOut}
          >
            <sphereGeometry args={[0.055, 14, 14]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2.2} />
          </mesh>
          {/* Halo — also clickable */}
          <mesh onClick={handleClick} onPointerOver={handlePointerOver} onPointerOut={handlePointerOut}>
            <sphereGeometry args={[0.088, 10, 10]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={0.3}
              transparent
              opacity={0.2}
              depthWrite={false}
            />
          </mesh>
        </>
      )}

      <Html position={[0, 0.14, 0]} center distanceFactor={12} style={{ pointerEvents: "none" }}>
        <div
          className="rounded border border-blue-300/45 bg-[#1f3f86]/88 px-2 py-1 text-[10px] font-mono text-blue-100 shadow-[0_2px_10px_rgba(15,23,42,0.35)] transition-all duration-200"
          style={{
            opacity: isHovered ? 1 : 0,
            transform: `translateY(${isHovered ? "0px" : "4px"})`,
            whiteSpace: "nowrap",
          }}
        >
          {label.title}
          <span className="ml-1 opacity-70">· {label.group}</span>
        </div>
      </Html>
    </group>
  );
}

function ComponentDots({
  statuses,
  onDotClick,
}: {
  statuses: ComponentStatuses;
  onDotClick?: DotClickHandler;
}) {
  return (
    <>
      {(Object.keys(HOTSPOTS) as DotKey[]).map(key => (
        <AlertDot
          key={key}
          dotKey={key}
          position={HOTSPOTS[key]}
          status={statuses[key]}
          onDotClick={onDotClick}
        />
      ))}
    </>
  );
}

// ── Blueprint-aware material ──────────────────────────────────────────────────

function Material({
  color,
  metalness = 0.22,
  roughness = 0.42,
  emissive,
  emissiveIntensity = 0,
  clearcoat = 0,
}: {
  color: string;
  metalness?: number;
  roughness?: number;
  emissive?: string;
  emissiveIntensity?: number;
  clearcoat?: number;
}) {
  const bp = useContext(BlueprintCtx);
  if (bp) {
    return (
      <>
        <meshStandardMaterial
          color="#3554A7"
          emissive="#AFC3EE"
          emissiveIntensity={0.28}
          transparent
          opacity={0.4}
        />
        <Edges color="#F4F8FF" threshold={8} />
      </>
    );
  }
  return (
    <meshPhysicalMaterial
      color={color}
      metalness={metalness}
      roughness={roughness}
      clearcoat={clearcoat}
      clearcoatRoughness={0.48}
      emissive={emissive ?? color}
      emissiveIntensity={emissiveIntensity}
    />
  );
}

// ── Machine model subcomponents ───────────────────────────────────────────────

function HpLogoDecal() {
  const bp   = useContext(BlueprintCtx);
  const logo = useTexture(hpLogoImage.src);
  if (bp) return null;
  return (
    <mesh position={[-0.03, 0.45, 0.688]}>
      <planeGeometry args={[0.34, 0.34]} />
      <meshBasicMaterial map={logo} transparent />
    </mesh>
  );
}

function BlueHandle({ position, height = 0.38 }: { position: Vector3Tuple; height?: number }) {
  return (
    <group position={position}>
      <RoundedBox args={[0.055, height, 0.04]} radius={0.018} smoothness={4}>
        <Material color="#8de3ff" metalness={0.16} roughness={0.22} emissive="#35c7ff" emissiveIntensity={0.2} />
      </RoundedBox>
      <mesh position={[0.036, 0, -0.008]}>
        <boxGeometry args={[0.012, height * 0.88, 0.012]} />
        <Material color="#1c2328" metalness={0.35} roughness={0.28} />
      </mesh>
    </group>
  );
}

function LevelingFoot({ position }: { position: Vector3Tuple }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.1, 0]}>
        <cylinderGeometry args={[0.026, 0.026, 0.2, 18]} />
        <Material color="#151719" metalness={0.48} roughness={0.32} />
      </mesh>
      <mesh position={[0, -0.018, 0]}>
        <cylinderGeometry args={[0.072, 0.052, 0.036, 28]} />
        <Material color="#202326" metalness={0.42} roughness={0.36} />
      </mesh>
    </group>
  );
}

function ControlTower() {
  const bp = useContext(BlueprintCtx);
  return (
    <group position={[-1.82, 1.09, 0]}>
      <RoundedBox args={[0.72, 2.18, 0.72]} radius={0.035} smoothness={5}>
        <Material color="#151718" metalness={0.46} roughness={0.28} clearcoat={0.26} />
      </RoundedBox>
      <RoundedBox args={[0.52, 0.34, 0.045]} radius={0.018} position={[0, 0.54, 0.385]} smoothness={4}>
        <Material color="#0b0d0e" metalness={0.28} roughness={0.24} />
      </RoundedBox>
      {!bp && (
        <mesh position={[0, 0.54, 0.412]}>
          <planeGeometry args={[0.38, 0.22]} />
          <meshStandardMaterial color="#d9f7ff" emissive="#7ddcff" emissiveIntensity={0.24} roughness={0.28} />
        </mesh>
      )}
      <RoundedBox args={[0.25, 0.13, 0.04]} radius={0.014} position={[0, 0.18, 0.385]} smoothness={4}>
        <Material color="#0c1215" metalness={0.32} roughness={0.3} emissive="#22b9ff" emissiveIntensity={0.09} />
      </RoundedBox>
      {[-0.42, -0.35, -0.28, -0.21, -0.14, -0.07].map((y) => (
        <mesh key={y} position={[0.05, y, 0.388]}>
          <boxGeometry args={[0.31, 0.018, 0.02]} />
          <Material color="#070809" metalness={0.18} roughness={0.54} />
        </mesh>
      ))}
      <RoundedBox args={[0.2, 0.58, 0.16]} radius={0.02} position={[-0.38, -0.62, -0.25]} smoothness={4}>
        <Material color="#101314" metalness={0.25} roughness={0.42} />
      </RoundedBox>
    </group>
  );
}

function TopHood() {
  const panels = [-0.85, -0.28, 0.29, 0.86, 1.43];
  return (
    <group>
      <RoundedBox args={[2.92, 0.3, 0.98]} radius={0.028} position={[0.37, 1.55, 0]} smoothness={4}>
        <Material color="#393b3b" metalness={0.42} roughness={0.25} clearcoat={0.18} />
      </RoundedBox>
      {panels.map((x) => (
        <mesh key={x} position={[x, 1.55, 0.505]}>
          <boxGeometry args={[0.018, 0.25, 0.018]} />
          <Material color="#17191a" metalness={0.34} roughness={0.34} />
        </mesh>
      ))}
      <mesh position={[0.42, 1.33, 0.49]} rotation={[0.18, 0, 0]}>
        <boxGeometry args={[2.78, 0.08, 0.12]} />
        <Material color="#101314" metalness={0.38} roughness={0.24} />
      </mesh>
      <RoundedBox args={[2.45, 0.1, 0.08]} radius={0.018} position={[0.47, 1.19, 0.54]} smoothness={4}>
        <Material color="#111415" metalness={0.54} roughness={0.18} clearcoat={0.18} />
      </RoundedBox>
      <mesh position={[1.22, 1.2, 0.592]}>
        <boxGeometry args={[0.78, 0.035, 0.026]} />
        <Material color="#7ee3ff" metalness={0.08} roughness={0.2} emissive="#34caff" emissiveIntensity={0.36} />
      </mesh>
      <mesh position={[0.17, 1.25, 0.56]}>
        <boxGeometry args={[1.08, 0.035, 0.025]} />
        <Material color="#1a1d1e" metalness={0.2} roughness={0.32} />
      </mesh>
    </group>
  );
}

function PowderPort() {
  return (
    <group position={[0.05, 1.82, 0.02]}>
      <mesh>
        <cylinderGeometry args={[0.21, 0.28, 0.16, 48]} />
        <Material color="#242728" metalness={0.5} roughness={0.28} />
      </mesh>
      <mesh position={[0, 0.11, 0]}>
        <cylinderGeometry args={[0.19, 0.19, 0.18, 48]} />
        <Material color="#111314" metalness={0.55} roughness={0.24} />
      </mesh>
      <mesh position={[0, 0.21, 0]}>
        <cylinderGeometry args={[0.22, 0.18, 0.05, 48]} />
        <Material color="#1e2021" metalness={0.58} roughness={0.26} />
      </mesh>
    </group>
  );
}

function FrontCabinets() {
  return (
    <group>
      <RoundedBox args={[1.02, 1.05, 0.08]} radius={0.025} position={[-0.33, 0.58, 0.56]} smoothness={4}>
        <Material color="#e0e2e3" metalness={0.16} roughness={0.33} clearcoat={0.16} />
      </RoundedBox>
      <RoundedBox args={[0.92, 0.98, 0.08]} radius={0.025} position={[0.78, 0.54, 0.56]} smoothness={4}>
        <Material color="#d7d9da" metalness={0.16} roughness={0.34} clearcoat={0.16} />
      </RoundedBox>
      <RoundedBox args={[0.66, 1.28, 0.1]} radius={0.02} position={[-0.02, 0.45, 0.62]} smoothness={4}>
        <Material color="#e8e9e9" metalness={0.12} roughness={0.32} clearcoat={0.2} />
      </RoundedBox>
      <HpLogoDecal />
      <BlueHandle position={[-0.73, 0.56, 0.625]} />
      <BlueHandle position={[0.86, 0.56, 0.625]} height={0.34} />
      <mesh position={[1.31, 0.43, 0.616]}>
        <boxGeometry args={[0.038, 0.62, 0.03]} />
        <Material color="#1d2021" metalness={0.28} roughness={0.28} />
      </mesh>
      <mesh position={[1.31, 0.43, 0.638]}>
        <boxGeometry args={[0.016, 0.46, 0.014]} />
        <Material color="#747b7e" metalness={0.24} roughness={0.24} />
      </mesh>
      {[-0.84, -0.78, 0.74, 0.8].map((x) => (
        <mesh key={x} position={[x, 1.04, 0.616]}>
          <cylinderGeometry args={[0.015, 0.015, 0.012, 18]} />
          <Material color="#3f95d6" emissive="#3f95d6" emissiveIntensity={0.16} />
        </mesh>
      ))}
    </group>
  );
}

function BuildBed() {
  return (
    <group>
      <RoundedBox args={[1.35, 0.1, 0.52]} radius={0.02} position={[0.14, 1.11, 0.33]} smoothness={4}>
        <Material color="#0f1112" metalness={0.48} roughness={0.2} />
      </RoundedBox>
      <mesh position={[0.14, 1.17, 0.36]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.12, 0.34]} />
        <Material color="#222528" metalness={0.38} roughness={0.18} />
      </mesh>
      <mesh position={[0.16, 1.184, 0.522]}>
        <boxGeometry args={[0.82, 0.012, 0.012]} />
        <Material color="#caa96b" metalness={0.2} roughness={0.24} emissive="#caa96b" emissiveIntensity={0.07} />
      </mesh>
      <mesh position={[0.92, 1.1, 0.35]}>
        <boxGeometry args={[0.032, 0.09, 0.52]} />
        <Material color="#303335" metalness={0.34} roughness={0.3} />
      </mesh>
    </group>
  );
}

function SideAndRearDetails() {
  return (
    <group>
      <RoundedBox args={[0.44, 0.34, 0.05]} radius={0.018} position={[-1.83, -0.18, 0.39]} smoothness={4}>
        <Material color="#0d0f10" metalness={0.22} roughness={0.48} />
      </RoundedBox>
      {[-0.27, -0.21, -0.15, -0.09].map((y) => (
        <mesh key={y} position={[-1.83, y, 0.423]}>
          <boxGeometry args={[0.29, 0.018, 0.02]} />
          <Material color="#313638" metalness={0.2} roughness={0.45} />
        </mesh>
      ))}
      <mesh position={[-2.185, 0.14, 0.05]}>
        <boxGeometry args={[0.035, 0.12, 0.18]} />
        <Material color="#d22e2e" emissive="#d22e2e" emissiveIntensity={0.18} roughness={0.25} />
      </mesh>
      <mesh position={[1.67, 0.58, 0.08]}>
        <boxGeometry args={[0.035, 0.14, 0.26]} />
        <Material color="#d1d4d5" metalness={0.18} roughness={0.4} />
      </mesh>
    </group>
  );
}

export type HpMetalJetS100ModelProps = {
  position?: Vector3Tuple;
  rotation?: Vector3Tuple;
  scale?: number;
  statuses?: ComponentStatuses;
  onDotClick?: DotClickHandler;
};

export function HpMetalJetS100Model({
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  scale = 1,
  statuses,
  onDotClick,
}: HpMetalJetS100ModelProps) {
  return (
    <group position={position} rotation={rotation} scale={scale}>
      <group position={[0, 0.09, 0]}>
        <ControlTower />
        <RoundedBox args={[2.85, 0.92, 1.02]} radius={0.035} position={[0.26, 0.63, 0]} smoothness={5}>
          <Material color="#cfd1d1" metalness={0.18} roughness={0.34} clearcoat={0.16} />
        </RoundedBox>
        <RoundedBox args={[2.9, 0.22, 1.0]} radius={0.025} position={[0.32, 1.03, 0]} smoothness={4}>
          <Material color="#202324" metalness={0.48} roughness={0.22} clearcoat={0.12} />
        </RoundedBox>
        <FrontCabinets />
        <BuildBed />
        <TopHood />
        <PowderPort />
        <SideAndRearDetails />
        {[
          [-2.11, -0.03, 0.32], [-1.55, -0.03, -0.31],
          [-0.82, -0.03, 0.48], [ 0.23, -0.03,  0.48],
          [ 1.45, -0.03, 0.48], [ 1.48, -0.03, -0.38],
        ].map((foot) => (
          <LevelingFoot key={foot.join(",")} position={foot as Vector3Tuple} />
        ))}
        {statuses && <ComponentDots statuses={statuses} onDotClick={onDotClick} />}
      </group>
    </group>
  );
}

// ── Scene ─────────────────────────────────────────────────────────────────────

function ModelScene({
  statuses,
  blueprintMode,
  onDotClick,
}: {
  statuses?: ComponentStatuses;
  blueprintMode?: boolean;
  onDotClick?: DotClickHandler;
}) {
  const bp = !!blueprintMode;
  const [focusWorld, setFocusWorld] = useState<THREE.Vector3 | null>(null);
  const [isUserControlling, setIsUserControlling] = useState(false);
  const autoRotateResumeRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (autoRotateResumeRef.current) clearTimeout(autoRotateResumeRef.current);
    };
  }, []);

  function handleDotClick(key: DotKey) {
    setFocusWorld(hotspotWorldPos(key));
    onDotClick?.(key);
  }

  function handleControlStart() {
    if (autoRotateResumeRef.current) {
      clearTimeout(autoRotateResumeRef.current);
      autoRotateResumeRef.current = null;
    }
    setIsUserControlling(true);
  }

  function handleControlEnd() {
    if (autoRotateResumeRef.current) clearTimeout(autoRotateResumeRef.current);
    // Keep user control "authoritative" briefly, then resume auto-rotation.
    autoRotateResumeRef.current = setTimeout(() => {
      setIsUserControlling(false);
      autoRotateResumeRef.current = null;
    }, 2500);
  }

  return (
    <BlueprintCtx.Provider value={bp}>
      <Canvas camera={{ position: [4.4, 2.5, 4.9], fov: 34 }} dpr={[1, 2]} shadows={!bp}>
        <color attach="background" args={[bp ? "#405CB1" : "#2F4F9E"]} />

        {bp ? (
          <>
            <ambientLight intensity={1.4} color="#98AEDD" />
            <directionalLight position={[4.8, 6.2, 4.2]}  intensity={1.6} color="#E4EAF6" />
            <directionalLight position={[-4.2, 3,  -3.6]} intensity={0.6} color="#405CB1" />
            <pointLight       position={[-1.9, 1.4, 1.2]} intensity={1.4} color="#E4EAF6" />
          </>
        ) : (
          <>
            <ambientLight intensity={0.62} color="#C7D6F7" />
            <directionalLight position={[4.8, 6.2, 4.2]}  intensity={2.25} color="#E8F0FF" castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
            <directionalLight position={[-4.2, 3,  -3.6]} intensity={0.58} color="#6F8FD8" />
            <pointLight       position={[-1.9, 1.4, 1.2]} intensity={1.0}  color="#9FE3FF" />
            <Environment preset="warehouse" />
          </>
        )}

        <group rotation={[0, -0.42, 0]} position={[0, -0.78, 0]}>
          {bp ? (
            <Grid
              position={[0, -0.012, 0]}
              cellSize={0.25}
              cellThickness={0.6}
              cellColor="#E4EAF6"
              sectionSize={1}
              sectionThickness={1.6}
              sectionColor="#E4EAF6"
              fadeDistance={14}
              fadeStrength={2.2}
              infiniteGrid
            />
          ) : (
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.012, 0]} receiveShadow>
              <planeGeometry args={[8, 6]} />
              <meshStandardMaterial color="#1C2B56" roughness={0.84} metalness={0.08} />
            </mesh>
          )}
          <HpMetalJetS100Model statuses={statuses} onDotClick={handleDotClick} />
        </group>

        {!bp && (
          <ContactShadows position={[0, -0.79, 0]} opacity={0.46} blur={1.8} scale={5.5} far={4} />
        )}

        <CameraFocuser focusWorld={focusWorld} />

        <OrbitControls
          makeDefault
          enablePan={false}
          enableDamping
          autoRotate={bp && !isUserControlling}
          autoRotateSpeed={0.6}
          target={[0, 0.42, 0]}
          minDistance={3.1}
          maxDistance={7.2}
          maxPolarAngle={1.42}
          onStart={handleControlStart}
          onEnd={handleControlEnd}
        />
      </Canvas>
    </BlueprintCtx.Provider>
  );
}

export function MachineExperience({
  statuses,
  blueprintMode,
  onDotClick,
}: {
  statuses?: ComponentStatuses;
  blueprintMode?: boolean;
  onDotClick?: DotClickHandler;
}) {
  return (
    <div className="h-full w-full overflow-hidden" style={{ background: blueprintMode ? "#405CB1" : "#2F4F9E" }}>
      <ModelScene statuses={statuses} blueprintMode={blueprintMode} onDotClick={onDotClick} />
    </div>
  );
}
