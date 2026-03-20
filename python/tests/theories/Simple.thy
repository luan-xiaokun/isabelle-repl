theory Simple
  imports Main
begin

lemma trivial: "True"
  by simp

lemma add_comm_nat: "(x :: nat) + y = y + x"
  by simp

lemma conj_easy: "\<lbrakk>P; Q\<rbrakk> \<Longrightarrow> P \<and> Q"
  by blast

lemma nat_not_zero: "(n :: nat) > 0 \<Longrightarrow> n \<noteq> 0"
  by simp

end
