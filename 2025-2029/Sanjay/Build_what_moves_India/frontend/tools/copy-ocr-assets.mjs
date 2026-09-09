import { copyFile, mkdir, readFile, stat } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const outputRoot = join(root, 'public', 'ocr')
const expected = {
  'worker.min.js': ['node_modules/tesseract.js/dist/worker.min.js', '576b7df7e3393e137e51849357c9adb53fe7ac1bb69bfa06cf3d61520f182c6d'],
  'core/tesseract-core-lstm.js': ['node_modules/tesseract.js-core/tesseract-core-lstm.js', '6510efc4e8b45c5465df30679b9911ffe0071cd2ee982fa064e6f5136ef2de85'],
  'core/tesseract-core-lstm.wasm.js': ['node_modules/tesseract.js-core/tesseract-core-lstm.wasm.js', 'eef5f8b2f8e20e150680b20adaec4a60babafee3adbe8a94583c81fee46e8680'],
  'core/tesseract-core-relaxedsimd-lstm.js': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd-lstm.js', 'a37ac78b707e8d5d3d2e532cc3c4e69b04d127ea44a608f1e7de17640402aa5c'],
  'core/tesseract-core-relaxedsimd-lstm.wasm.js': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js', '861a536cf9ef8e63cb644d57bab39c388f37f7d6b6f60024b741c5f6b39a59b3'],
  'core/tesseract-core-relaxedsimd.js': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd.js', '716be037611f21b568347421f582f1e1a6456b6d5c3a7c2406c8a2a6c0136427'],
  'core/tesseract-core-relaxedsimd.wasm.js': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd.wasm.js', '843074aa5bad1cc6421b74a86201768ced9f244795e4d81435435a61a40ce535'],
  'core/tesseract-core-simd-lstm.js': ['node_modules/tesseract.js-core/tesseract-core-simd-lstm.js', 'e48e2f02ddae3716c8dd24bf41cd290d4efa96892d689cdc4013c2545d63f469'],
  'core/tesseract-core-simd-lstm.wasm.js': ['node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm.js', 'c58b46a4c796c0b8afccf77591d5b875b6896b45d402bbce8caa6f5362447b38'],
  'core/tesseract-core-simd.js': ['node_modules/tesseract.js-core/tesseract-core-simd.js', 'da428fd7989ba749855ea16718a83b23e7ce04016fe31866ad2735813efc7133'],
  'core/tesseract-core-simd.wasm.js': ['node_modules/tesseract.js-core/tesseract-core-simd.wasm.js', '6b61ef4e911b5cf57e656bbfe983d6e2b3711a02dd164154ddda064566e8e09d'],
  'core/tesseract-core.js': ['node_modules/tesseract.js-core/tesseract-core.js', 'a824c1b99a19e122d87e4467fe16aabb56c495d6cc9a08bc58cb8a7342636b43'],
  'core/tesseract-core.wasm.js': ['node_modules/tesseract.js-core/tesseract-core.wasm.js', '0bc6ce3e5fbbd0cd89706cf2fd70960e3372f4f01ee24265b26990808aaeb286'],
  'core/tesseract-core-lstm.wasm': ['node_modules/tesseract.js-core/tesseract-core-lstm.wasm', '66b17df6e20c5329a17ffa9c202a47eaa3e32500b253d4c7f38e7f2bc01457c3'],
  'core/tesseract-core-relaxedsimd-lstm.wasm': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm', '7985c92d4c64e7267d24cadffe1b2a1da6bf8aa55fdcaf953fe94fe122a24545'],
  'core/tesseract-core-relaxedsimd.wasm': ['node_modules/tesseract.js-core/tesseract-core-relaxedsimd.wasm', '45f8c9b516df326b6ae6b493ed3a6289df5cbd10490e7b6ff8bf5b12ea42d1da'],
  'core/tesseract-core-simd-lstm.wasm': ['node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm', '34e8d50cac216427d86bf397d610fdd9f49492539bbcdfbfccc4eda20c810bea'],
  'core/tesseract-core-simd.wasm': ['node_modules/tesseract.js-core/tesseract-core-simd.wasm', '7d237a13edfeb0fa2f104744fccde0a00e0c076c3e23b7a8fc7af75ec9af2c3e'],
  'core/tesseract-core.wasm': ['node_modules/tesseract.js-core/tesseract-core.wasm', 'c7f5ace62ac0ad065e71e9c6725f1d7cdf82e7eda8fba532cbb9563964da7098'],
  'lang/eng.traineddata.gz': ['node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz', '45b4cb346724ac1774f1c36f42f182b887bcdb28ebe63e6fff90ac41f3fcff91'],
  'lang/hin.traineddata.gz': ['node_modules/@tesseract.js-data/hin/4.0.0_best_int/hin.traineddata.gz', 'f3b6a0d320df38d886178cdd727b90dbf9df3db053adb32bd9cf73f0463cda07'],
  'lang/mal.traineddata.gz': ['node_modules/@tesseract.js-data/mal/4.0.0_best_int/mal.traineddata.gz', 'a4a5b24474889dbbe9943bb3cb7b24819c1cd594f2f371340bba83c30fd81bf0'],
}

const digest = async path => createHash('sha256').update(await readFile(path)).digest('hex')
const checkOnly = process.argv.includes('--check')
let totalBytes = 0

for (const [output, [source, checksum]] of Object.entries(expected)) {
  const sourcePath = join(root, source)
  if (await digest(sourcePath) !== checksum) throw new Error(`OCR dependency integrity mismatch: ${source}`)
  const outputPath = join(outputRoot, output)
  if (!checkOnly) {
    await mkdir(dirname(outputPath), { recursive: true })
    await copyFile(sourcePath, outputPath)
  }
  if (await digest(outputPath) !== checksum) throw new Error(`Packaged OCR asset integrity mismatch: ${output}`)
  totalBytes += (await stat(outputPath)).size
}

process.stdout.write(JSON.stringify({ assets: Object.keys(expected).length, totalBytes, mode: checkOnly ? 'check' : 'copy' }) + '\n')
