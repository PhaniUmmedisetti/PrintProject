import { useReducer } from 'react'
import { AnimatePresence } from 'framer-motion'
import type { StartPrintResponse } from './api/piBackend'

import LandingScreen from './screens/LandingScreen'
import QRScreen from './screens/QRScreen'
import KeypadScreen from './screens/KeypadScreen'
import PreviewScreen from './screens/PreviewScreen'
import PrintingScreen from './screens/PrintingScreen'
import SuccessScreen from './screens/SuccessScreen'
import ErrorScreen from './screens/ErrorScreen'

// ── State machine ────────────────────────────────────────────────────────────

type Screen = 'LANDING' | 'QR_CODE' | 'KEYPAD' | 'PREVIEW' | 'PRINTING' | 'SUCCESS' | 'ERROR'

interface AppState {
  screen: Screen
  job: StartPrintResponse | null
  errorMsg: string
}

type Action =
  | { type: 'GO_QR' }
  | { type: 'GO_KEYPAD' }
  | { type: 'CODE_ACCEPTED'; job: StartPrintResponse }
  | { type: 'CONFIRM_PRINT' }
  | { type: 'PRINT_DONE' }
  | { type: 'ERROR'; msg: string }
  | { type: 'RETRY' }
  | { type: 'RESET' }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'GO_QR':      return { ...state, screen: 'QR_CODE' }
    case 'GO_KEYPAD':  return { ...state, screen: 'KEYPAD' }
    case 'CODE_ACCEPTED': return { ...state, screen: 'PREVIEW', job: action.job }
    case 'CONFIRM_PRINT': return { ...state, screen: 'PRINTING' }
    case 'PRINT_DONE': return { ...state, screen: 'SUCCESS' }
    case 'ERROR':      return { ...state, screen: 'ERROR', errorMsg: action.msg }
    case 'RETRY':      return { ...state, screen: 'KEYPAD', job: null, errorMsg: '' }
    case 'RESET':      return { screen: 'LANDING', job: null, errorMsg: '' }
    default:           return state
  }
}

const initial: AppState = { screen: 'LANDING', job: null, errorMsg: '' }

// ── Root component ───────────────────────────────────────────────────────────

export default function App() {
  const [state, dispatch] = useReducer(reducer, initial)

  const screen = (() => {
    switch (state.screen) {
      case 'LANDING':  return <LandingScreen onPrintNow={() => dispatch({ type: 'GO_QR' })} />
      case 'QR_CODE':  return <QRScreen
                                onBack={() => dispatch({ type: 'RESET' })}
                                onEnterCode={() => dispatch({ type: 'GO_KEYPAD' })} />
      case 'KEYPAD':   return <KeypadScreen
                                onBack={() => dispatch({ type: 'GO_QR' })}
                                onCodeAccepted={job => dispatch({ type: 'CODE_ACCEPTED', job })}
                                onError={msg => dispatch({ type: 'ERROR', msg })} />
      case 'PREVIEW':  return <PreviewScreen
                                job={state.job!}
                                onConfirm={() => dispatch({ type: 'CONFIRM_PRINT' })}
                                onError={msg => dispatch({ type: 'ERROR', msg })} />
      case 'PRINTING': return <PrintingScreen
                                jobId={state.job!.job_id}
                                onDone={() => dispatch({ type: 'PRINT_DONE' })}
                                onError={msg => dispatch({ type: 'ERROR', msg })} />
      case 'SUCCESS':  return <SuccessScreen onDone={() => dispatch({ type: 'RESET' })} />
      case 'ERROR':    return <ErrorScreen
                                message={state.errorMsg}
                                onRetry={() => dispatch({ type: 'RETRY' })}
                                onCancel={() => dispatch({ type: 'RESET' })} />
    }
  })()

  return (
    <div className="kiosk-shell">
      <div className="kiosk-frame">
        <AnimatePresence mode="wait">
          {screen}
        </AnimatePresence>
      </div>
    </div>
  )
}
