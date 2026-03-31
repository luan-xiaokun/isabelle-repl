theory ClassLocalTheoryInfo
  imports Main
begin

class foo_class =
  fixes f :: "'a => 'a"
begin

lemma foo_class_refl: "f x = f x"
  by simp

end

end
