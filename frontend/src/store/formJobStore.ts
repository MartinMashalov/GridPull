import { create } from 'zustand'

export type FormJobStatus = 'processing' | 'complete' | 'error'

export interface FormJob {
  id: string
  targetName: string
  sourceCount: number
  status: FormJobStatus
  resultBlob?: Blob
  resultName?: string
  errorMsg?: string
}

interface FormJobState {
  jobs: FormJob[]
  addJob: (job: FormJob) => void
  addJobs: (jobs: FormJob[]) => void
  updateJob: (id: string, update: Partial<FormJob>) => void
  dismissJob: (id: string) => void
}

export const useFormJobStore = create<FormJobState>((set) => ({
  jobs: [],
  addJob: (job) => set((state) => ({ jobs: [job, ...state.jobs] })),
  addJobs: (jobs) => set((state) => ({ jobs: [...jobs, ...state.jobs] })),
  updateJob: (id, update) => set((state) => ({
    jobs: state.jobs.map(j => j.id === id ? { ...j, ...update } : j),
  })),
  dismissJob: (id) => set((state) => ({ jobs: state.jobs.filter(j => j.id !== id) })),
}))
