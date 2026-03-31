theory LocalTheoryInfo
  imports Main
begin

locale foo =
  fixes x :: nat
begin

lemma foo_refl: "x = x"
  by simp

context
begin

lemma nested_refl: "x = x"
  by simp

end

end

context
begin

lemma global_ctx: "True"
  by simp

end

end
