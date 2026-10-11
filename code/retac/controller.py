
class ReTACController:
    """State-flow outline: native -> residual refinement -> verify -> recover.

    Native routing may return DIRECT. On refinement, verification runs in
    planning/perception/reasoning order and stops at the first non-passing stage.
    T counts recovery actions, with verification at both t=0 and t=T. Final
    status is VERIFIED or UNVERIFIED. 
    """

    def __init__(self, model, tools, recovery_budget=2):
        if type(recovery_budget) is not int or recovery_budget < 0:
            raise ValueError("recovery_budget must be a nonnegative integer")
        self.model = model
        self.tools = tools
        self.recovery_budget = recovery_budget

    def run(self, task_input):
        """Full native-routing/refinement/verification loop; not yet released."""
        
    def native_attempt(self, task_input):
        """Native requirements, evidence, unresolved IDs, and candidate answer."""
        
    def plan(self, task_input, native_state, operation_interfaces):
        """Residual plan with primitive or dynamically composed acquisition steps."""

    def perceive(self, task_input, plan, operation_interfaces):
        """Dependency-ordered tool execution and registration of new evidence."""

    def merge_evidence(self, native_evidence, supplementary_evidence):
        """Preserve source records, dependencies, and conflicting observations."""
        
    def reason(self, question, options, plan, active_evidence, history=None, feedback=None):
        """Evidence-grounded reasoning; does not acquire new visual observations."""
        
    def verify(self, task_input, operation_interfaces, state, cache):
        """Stage-specific input isolation, criterion checks, and valid cache reuse."""
        
    def resolve_concerns(self, task_input, state, verdicts, diagnosis, cache):
        """Recheck only implicated upstream criteria before routing recovery."""
        
    def route(self, verdicts, diagnosis):
        """ACCEPT, a supported recovery action, or no supported revision."""
        
    def recover(self, task_input, plan, active_evidence, history, feedback):
        """REPLAN / REPERCEIVE / REREASON, preserving unaffected state."""
        
    def invalidate(self, cache, changed_records, dependencies):
        """Invalidate changed records and their transitive dependents."""
        
