import { CreditCard, ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'

interface Props {
  description?: string
}

export default function CreditCardBanner({
  description = "Add a credit card to start processing documents. You won't be charged on the free plan.",
}: Props) {
  const navigate = useNavigate()
  const { user } = useAuthStore()

  if (!user || user.has_card) return null

  return (
    <div className="relative mb-4 rounded-xl border border-primary/30 bg-primary/5 p-4 flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
        <CreditCard size={15} className="text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">Credit card required</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <Button size="sm" type="button" onClick={() => navigate('/settings?tab=payment')} className="flex-shrink-0">
        Add Card <ArrowRight size={12} className="ml-1" />
      </Button>
    </div>
  )
}
