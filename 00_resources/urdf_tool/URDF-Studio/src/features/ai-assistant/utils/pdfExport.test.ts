import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'

import {
  __setPdfCanvasFactoryForTests,
  __setPdfGenerationDepsLoaderForTests
} from '@/features/file-io/utils/generatePdfFromHtml'
import { exportInspectionReportPdf } from './pdfExport.ts'

function waitForTimers(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0))
}

function restoreGlobalProperty<T extends keyof typeof globalThis>(
  key: T,
  originalValue: (typeof globalThis)[T] | undefined
) {
  if (originalValue === undefined) {
    delete globalThis[key]
    return
  }

  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value: originalValue
  })
}

function installDomEnvironment() {
  const originalWindow = globalThis.window
  const originalDocument = globalThis.document
  const originalNavigator = globalThis.navigator
  const originalHTMLElement = globalThis.HTMLElement
  const originalSVGElement = globalThis.SVGElement
  const originalNode = globalThis.Node
  const originalMutationObserver = globalThis.MutationObserver
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame
  const originalDOMParser = globalThis.DOMParser

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/'
  })

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: dom.window
  })
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    writable: true,
    value: dom.window.document
  })
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value: dom.window.navigator
  })
  Object.defineProperty(globalThis, 'HTMLElement', {
    configurable: true,
    writable: true,
    value: dom.window.HTMLElement
  })
  Object.defineProperty(globalThis, 'SVGElement', {
    configurable: true,
    writable: true,
    value: dom.window.SVGElement
  })
  Object.defineProperty(globalThis, 'Node', {
    configurable: true,
    writable: true,
    value: dom.window.Node
  })
  Object.defineProperty(globalThis, 'MutationObserver', {
    configurable: true,
    writable: true,
    value: dom.window.MutationObserver
  })
  Object.defineProperty(globalThis, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: (callback: FrameRequestCallback) => setTimeout(() => callback(Date.now()), 0)
  })
  Object.defineProperty(globalThis, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: (handle: number) => clearTimeout(handle)
  })
  Object.defineProperty(globalThis, 'DOMParser', {
    configurable: true,
    writable: true,
    value: dom.window.DOMParser
  })
  Object.defineProperty(dom.window, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: globalThis.requestAnimationFrame
  })
  Object.defineProperty(dom.window, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: globalThis.cancelAnimationFrame
  })
  Object.defineProperty(dom.window.document, 'fonts', {
    configurable: true,
    value: { ready: Promise.resolve() }
  })

  return {
    restore() {
      dom.window.close()
      restoreGlobalProperty('window', originalWindow)
      restoreGlobalProperty('document', originalDocument)
      restoreGlobalProperty('navigator', originalNavigator)
      restoreGlobalProperty('HTMLElement', originalHTMLElement)
      restoreGlobalProperty('SVGElement', originalSVGElement)
      restoreGlobalProperty('Node', originalNode)
      restoreGlobalProperty('MutationObserver', originalMutationObserver)
      restoreGlobalProperty('requestAnimationFrame', originalRequestAnimationFrame)
      restoreGlobalProperty('cancelAnimationFrame', originalCancelAnimationFrame)
      restoreGlobalProperty('DOMParser', originalDOMParser)
    }
  }
}

test('exportInspectionReportPdf renders the report into a hidden container and exports a multipage PDF without browser print', async () => {
  const dom = installDomEnvironment()
  const savedFiles: string[] = []
  const addedImages: Array<{ width: number; height: number }> = []
  let capturedText = ''
  let createdSliceCount = 0
  let printCallCount = 0

  Object.defineProperty(window, 'print', {
    configurable: true,
    writable: true,
    value: () => {
      printCallCount += 1
    }
  })

  __setPdfGenerationDepsLoaderForTests(async () => ({
    html2canvas: (async (element: HTMLElement) => {
      capturedText = element.textContent || ''
      return {
        width: 1200,
        height: 3600,
        getContext: () => ({
          fillStyle: '#ffffff',
          fillRect: () => {},
          drawImage: () => {}
        }),
        toDataURL: () => 'data:image/png;base64,source'
      } as any
    }) as any,
    jsPDF: class {
      internal = {
        pageSize: {
          getWidth: () => 210,
          getHeight: () => 297
        }
      }

      addImage(_image: string, _format: string, _x: number, _y: number, width: number, height: number) {
        addedImages.push({ width, height })
      }

      addPage() {}

      save(fileName: string) {
        savedFiles.push(fileName)
      }

      setProperties() {}
    } as any
  }))

  __setPdfCanvasFactoryForTests((width, height) => ({
    width,
    height,
    getContext: () => ({
      fillStyle: '#ffffff',
      fillRect: () => {},
      drawImage: () => {}
    }),
    toDataURL: () => {
      createdSliceCount += 1
      return `data:image/png;base64,slice-${createdSliceCount}`
    }
  }))

  try {
    await exportInspectionReportPdf({
      inspectionReport: {
        summary: '检测到 2 个问题，需要修复 armature 和 effort/velocity 限制。',
        issues: [
          {
            type: 'warning',
            title: 'armature 配置偏低',
            description: 'FL_hip_rotor 的等效转动惯量接近 0。',
            profileId: 'workflow.hardware_config',
            itemId: 'armature_equivalent_inertia',
          },
          {
            type: 'error',
            title: 'effort/velocity 缺失',
            description: 'Head_upper_joint 缺少 effort 和 velocity 限值。',
            profileId: 'workflow.hardware_config',
            itemId: 'effort_velocity_limits',
          }
        ],
        overallScore: 63,
        profileScores: {
          'workflow.hardware_config': 6.5
        },
        maxScore: 100
      },
      robotName: 'my_robot',
      lang: 'zh'
    })

    assert.match(capturedText, /检测到 2 个问题/)
    assert.match(capturedText, /硬件配置检查/)
    assert.match(capturedText, /armature 配置偏低/)
    assert.match(capturedText, /effort\/velocity 缺失/)
    assert.equal(printCallCount, 0)
    assert.equal(savedFiles.length, 1)
    assert.match(savedFiles[0], /^my_robot_检查报告_.*\.pdf$/)
    assert.ok(addedImages.length > 1, 'expected the rendered report to be split across multiple PDF pages')
    assert.ok(createdSliceCount > 1, 'expected multiple canvas slices for a long report')
    assert.equal(document.getElementById('pdf-report-container-modal'), null)
    assert.equal(document.querySelector('iframe'), null)
  } finally {
    __setPdfGenerationDepsLoaderForTests(null)
    __setPdfCanvasFactoryForTests(null)
    await waitForTimers()
    await waitForTimers()
    dom.restore()
  }
})
