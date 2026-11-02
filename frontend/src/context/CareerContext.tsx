import { createContext, useContext, type ReactNode } from 'react'
import { useCareerStore } from '../hooks/useCareerStore'
const CareerContext = createContext<ReturnType<typeof useCareerStore> | null>(null)
export function CareerProvider({ children }: {
  children: ReactNode
}) {
  const store = useCareerStore()
  return <CareerContext.Provider value={store}>{children}</CareerContext.Provider>
}
export function useCareer() {
  const context = useContext(CareerContext)
  if (!context)
    throw new Error('useCareer must be used inside CareerProvider')
  return context
}
