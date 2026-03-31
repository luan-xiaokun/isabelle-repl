theory BrokenReplay
  imports Main
begin

lemma good_before_failure: "True"
  by simp

lemma broken_replay: "True"
  by totally_nonexistent_tactic_xyz

end
