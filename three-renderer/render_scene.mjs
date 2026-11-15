import { mkdir } from "node:fs/promises";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index].replace(/^--/, ""), process.argv[index + 1]);
}

const output = path.resolve(args.get("output"));
const sceneId = Number.parseInt(args.get("scene-id")?.replace(/\D/g, "") || "1", 10);
const rendererDir = path.dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(rendererDir, ".browsers");
const { chromium } = await import("playwright");

await mkdir(path.dirname(output), { recursive: true });
const browser = await chromium.launch({
  headless: true,
  channel: "chromium",
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const server = createServer(async (request, response) => {
  const relative = request.url === "/" ? "scene.html" : request.url.slice(1);
  if (!relative.startsWith("node_modules/") && !["scene.html", "three-browser.mjs"].includes(relative)) {
    response.writeHead(404);
    response.end();
    return;
  }
  try {
    const body = await readFile(path.join(rendererDir, relative));
    const contentType = relative.endsWith(".html")
      ? "text/html"
      : relative.endsWith(".mjs")
        ? "text/javascript"
        : "text/javascript";
    response.writeHead(200, { "Content-Type": contentType });
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const serverPort = server.address().port;

try {
  const page = await browser.newPage({ viewport: { width: 768, height: 512 } });
  await page.goto(`http://127.0.0.1:${serverPort}/scene.html`);
  await page.waitForFunction(() => Boolean(window.THREE));
  await page.evaluate((frame) => {
    const THREE = window.THREE;
    const renderer = new THREE.WebGLRenderer({
      canvas: document.querySelector("#canvas"),
      antialias: true,
    });
    renderer.setSize(768, 512, false);
    renderer.setPixelRatio(1);
    renderer.shadowMap.enabled = true;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.setClearColor(0x15152a);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x15152a, 12, 30);
    const camera = new THREE.PerspectiveCamera(42, 768 / 512, 0.1, 100);
    const ambient = new THREE.HemisphereLight(0x9db7d6, 0x20202a, 2.2);
    scene.add(ambient);
    const lamp = new THREE.DirectionalLight(0xffd7a3, 3.2);
    lamp.position.set(4, 9, 5);
    lamp.castShadow = true;
    scene.add(lamp);

    const box = (size, color, position) => {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(...size),
        new THREE.MeshToonMaterial({ color }),
      );
      mesh.position.set(...position);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      scene.add(mesh);
      return mesh;
    };

    box([18, 0.2, 28], 0x242a34, [0, -0.1, 0]);
    box([18, 7, 0.2], 0x1b2533, [0, 3.5, -12]);
    box([0.2, 7, 28], 0x202936, [-9, 3.5, 0]);
    box([0.2, 7, 28], 0x202936, [9, 3.5, 0]);
    for (let index = -2; index <= 2; index += 1) {
      box([3.8, 1.8, 0.12], 0x30445a, [index * 3.6, 3.8, -11.8]);
      box([0.08, 3.8, 0.08], 0xe9b35d, [index * 3.6, 5.2, -11.65]);
    }
    for (let index = -1; index <= 1; index += 1) {
      box([0.12, 5.2, 0.12], 0xc98b4b, [index * 4.5, 2.6, -2]);
    }
    for (let index = -3; index <= 3; index += 1) {
      box([0.25, 0.08, 28], 0x4d5665, [index * 1.4, 0.02, 0]);
    }

    const character = new THREE.Group();
    const part = (size, color, position) => {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(...size),
        new THREE.MeshToonMaterial({ color }),
      );
      mesh.position.set(...position);
      mesh.castShadow = true;
      character.add(mesh);
    };
    part([1.5, 1.7, 1.35], 0x23a7a5, [0, 2.3, 0]);
    part([1.35, 1.3, 1.25], 0xd7a26e, [0, 4.0, 0]);
    part([0.26, 0.28, 0.12], 0x17202b, [-0.28, 4.1, -0.64]);
    part([0.26, 0.28, 0.12], 0x17202b, [0.28, 4.1, -0.64]);
    part([1.45, 0.35, 1.35], 0x172b3c, [0, 4.7, 0]);
    part([0.42, 1.5, 0.45], 0x23a7a5, [-1.0, 2.35, 0]);
    part([0.42, 1.5, 0.45], 0x23a7a5, [1.0, 2.35, 0]);
    part([0.55, 1.45, 0.55], 0x193b75, [-0.43, 0.8, 0]);
    part([0.55, 1.45, 0.55], 0x193b75, [0.43, 0.8, 0]);
    part([0.7, 0.35, 1.0], 0xe04452, [-0.43, 0.02, -0.08]);
    part([0.7, 0.35, 1.0], 0xe04452, [0.43, 0.02, -0.08]);
    const shot = (frame - 1) % 6;
    const characterPositions = [
      [0, 0, 2.5],
      [-3.1, 0, 0.5],
      [3.1, 0, 1.5],
      [0, 0, 5.2],
      [-2.2, 0, 4.2],
      [2.4, 0, 3.2],
    ];
    const characterPosition = characterPositions[shot];
    character.position.set(...characterPosition);
    character.rotation.y = [-0.15, 0.5, -0.5, Math.PI, 0.3, -0.3][shot];
    scene.add(character);

    const cameraPositions = [
      [0, 4.3, 11],
      [-7, 4.1, 8],
      [7, 4.6, 8],
      [0, 6.3, 7],
      [-5.5, 3.5, 5.5],
      [5.5, 3.8, 6.5],
    ];
    camera.position.set(...cameraPositions[shot]);
    camera.lookAt(characterPosition[0], 2.2, characterPosition[2]);
    renderer.render(scene, camera);
  }, sceneId);
  await page.screenshot({ path: output });
} finally {
  await new Promise((resolve) => server.close(resolve));
  await browser.close();
}
