theory SlowReplay
  imports Main
begin

lemma after_sleep: "True"
  apply (sleep 1)
  by simp

end
