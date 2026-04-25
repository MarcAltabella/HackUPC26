"use client";

import { ContactShadows, Environment, OrbitControls, RoundedBox, useTexture } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import hpLogoImage from "../data/HP_logo_2025.svg.png";

export const HP_METAL_JET_S100_DIMENSIONS = {
  widthMm: 2975,
  depthMm: 1350,
  heightMm: 2410,
  weightKg: 851,
};

type Vector3Tuple = [number, number, number];

export type HpMetalJetS100ModelProps = {
  position?: Vector3Tuple;
  rotation?: Vector3Tuple;
  scale?: number;
};

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

function HpLogoDecal() {
  const logo = useTexture(hpLogoImage.src);

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
  return (
    <group position={[-1.82, 1.09, 0]}>
      <RoundedBox args={[0.72, 2.18, 0.72]} radius={0.035} smoothness={5}>
        <Material color="#151718" metalness={0.46} roughness={0.28} clearcoat={0.26} />
      </RoundedBox>
      <RoundedBox args={[0.52, 0.34, 0.045]} radius={0.018} position={[0, 0.54, 0.385]} smoothness={4}>
        <Material color="#0b0d0e" metalness={0.28} roughness={0.24} />
      </RoundedBox>
      <mesh position={[0, 0.54, 0.412]}>
        <planeGeometry args={[0.38, 0.22]} />
        <meshStandardMaterial color="#d9f7ff" emissive="#7ddcff" emissiveIntensity={0.24} roughness={0.28} />
      </mesh>
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
        <meshStandardMaterial color="#222528" metalness={0.38} roughness={0.18} transparent opacity={0.82} />
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

export function HpMetalJetS100Model({
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  scale = 1,
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
          [-2.11, -0.03, 0.32],
          [-1.55, -0.03, -0.31],
          [-0.82, -0.03, 0.48],
          [0.23, -0.03, 0.48],
          [1.45, -0.03, 0.48],
          [1.48, -0.03, -0.38],
        ].map((foot) => (
          <LevelingFoot key={foot.join(",")} position={foot as Vector3Tuple} />
        ))}
      </group>
    </group>
  );
}

function ModelScene() {
  return (
    <Canvas camera={{ position: [4.4, 2.5, 4.9], fov: 34 }} dpr={[1, 2]} shadows>
      <color attach="background" args={["#050607"]} />
      <ambientLight intensity={0.42} />
      <directionalLight position={[4.8, 6.2, 4.2]} intensity={2.55} castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <directionalLight position={[-4.2, 3, -3.6]} intensity={0.52} />
      <pointLight position={[-1.9, 1.4, 1.2]} intensity={0.8} color="#9fe8ff" />
      <Environment preset="warehouse" />
      <group rotation={[0, -0.42, 0]} position={[0, -0.78, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.012, 0]} receiveShadow>
          <planeGeometry args={[8, 6]} />
          <meshStandardMaterial color="#0d1011" roughness={0.86} metalness={0.08} />
        </mesh>
        <HpMetalJetS100Model />
      </group>
      <ContactShadows position={[0, -0.79, 0]} opacity={0.46} blur={1.8} scale={5.5} far={4} />
      <OrbitControls enablePan={false} target={[0, 0.42, 0]} minDistance={3.1} maxDistance={7.2} maxPolarAngle={1.42} />
    </Canvas>
  );
}

export function MachineExperience() {
  return (
    <main className="h-screen min-h-screen overflow-hidden bg-[#050607]">
      <ModelScene />
    </main>
  );
}
