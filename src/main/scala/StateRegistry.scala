package isa.repl

import java.util.concurrent.ConcurrentHashMap

import scala.jdk.CollectionConverters._

import de.unruh.isabelle.pure.ToplevelState

/** Owns the global state_id -> session_id ownership mapping.
  *
  * Source-of-truth invariant:
  *   - if a state_id is live, its owner is recorded here
  *   - a missing owner means the state is not addressable through public APIs
  */
final class StateRegistry {
  private val stateOwnerMap = new ConcurrentHashMap[String, String]()

  def ownerOf(stateId: String): Option[String] =
    Option(stateOwnerMap.get(stateId))

  def registerState(
      sessionId: String,
      stateId: String,
      session: IsabelleSession,
      state: ToplevelState,
      cacheKey: Option[(os.Path, Int)] = None
  ): Unit = {
    session.storeStateLocal(stateId, state, cacheKey)
    stateOwnerMap.put(stateId, sessionId)
  }

  def isLiveStateInSession(
      sessionId: String,
      stateId: String,
      session: IsabelleSession
  ): Boolean =
    ownerOf(stateId).contains(sessionId) && session.hasStateLocal(stateId)

  def dropStateIfOwned(
      sessionId: String,
      stateId: String,
      session: IsabelleSession
  ): Boolean = {
    val removedOwner = stateOwnerMap.remove(stateId, sessionId)
    if (removedOwner) session.dropStateLocal(Seq(stateId))
    removedOwner
  }

  def groupStateIdsByOwner(stateIds: Seq[String]): Map[String, List[String]] =
    stateIds.distinct
      .flatMap(stateId =>
        ownerOf(stateId).map(sessionId => sessionId -> stateId)
      )
      .groupBy(_._1)
      .view
      .mapValues(_.map(_._2).toList)
      .toMap

  def dropAllStatesForSession(
      sessionId: String,
      session: IsabelleSession
  ): Unit = {
    val stateIds = stateOwnerMap
      .entrySet()
      .asScala
      .collect { case e if e.getValue == sessionId => e.getKey }
      .toList
    stateIds.foreach(stateId => stateOwnerMap.remove(stateId, sessionId))
    session.dropAllStatesLocal()
  }
}
