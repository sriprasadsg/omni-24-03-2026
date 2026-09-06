# Phase 65: FIM Process Attribution via Fanotify Research (Skipped)

## Goal
Add Linux fanotify-based PID → real process-tree attribution to FIM change events, fully satisfying FIM-02's "process tree" clause. Windows USN Journal equivalent optional.

## Dependencies
- Phase 64: rotate_key autonomous remediation (completes key rotation testing)

## Key Components to Implement

### 1. Core Fanotify Integration
- **Linux kernel fanotify API**: Monitor file access and modifications
- **PID tracking**: Map file events to process IDs
- **Process tree resolution**: Traverse parent-child process relationships
- **FIM integration**: Hook fanotify events into existing FIM data models

### 2. Architecture Components
- **Fanotify Watcher**: Linux kernel-level file system event monitoring
- **Process Mapper**: PID-to-process-tree resolution service
- **Event Corrector**: Match fanotify events with FIM events
- **Attribute Enricher**: Add process tree metadata to FIM event record

### 3. Technical Requirements
- **Real-time processing**: Handle high-volume FIM events without backlog
- **Performance**: Efficient PID resolution for hundreds of concurrent processes
- **Reliability**: Handle process forks, execve, and daemonization scenarios
- **Cross-platform**: Optional Windows USN Journal equivalent implementation

## Technology Stack Recommendations

### Core Libraries
| Library | Purpose | Implementation Notes |
|---------|---------|-------------------|
| fanotify.h (kernel) | Low-level file system event notification | Native Linux API |
| libpfm (performance) | Performance monitoring | Optional, for optimization |
| libtree (process trees) | Process hierarchy traversal | May use /proc/<pid>/status |

### System Integration
| Component | Technology | Reason |
|-----------|------------|--------|
| Process tracking | ptrace, /proc filesystem | Native Linux capabilities |
| Event correlation | Redis Pub/Sub | Fast inter-service communication |
| Data storage | PostgreSQL | Structured FIM storage |

## Implementation Patterns

### 1. Fanotify Event Capture
```c
// fanotify_init with FAN_ALL_EVENTS flags
// FAN_MODIFY, FAN_ACCESS, FAN_MOVED_FROM/TO, FAN_OPEN
```

### 2. Process Attribution
- **PID discovery**: Extract pid from fanotify event
- **Tree walking**: Recursively collect parent process IDs via /proc/<pid>/status
- **Event enrichment**: Attach process tree to FIM event metadata

### 3. FIM Integration
- **Event timing**: Correlate fanotify event timestamps with FIM recording
- **Resource identification**: Match fanotify paths to FIM tracked resources
- **Metadata addition**: Append process tree to FIM event record

## Performance Considerations

### Scaling Strategies
- **Event batching**: Aggregate related events before processing
- **Redis caching**: Cache process tree lookups
- **Async processing**: Offload heavy PID resolution to background workers

### Throughput Targets
- **Minimum**: 100 events/second
- **Recommended**: 1,000 events/second
- **Peak**: 10,000 events/second with optimizations

## Security Considerations

### Attack Surface Reduction
- **Privilege separation**: Run fanotify in unprivileged process with CAP_SYS_ADMIN
- **Input validation**: Validate all PIDs and paths before processing
- **Audit logging**: Log all process tree attributions for security review

### Compliance Requirements
- **Retention**: Process attribution data retained 90 days
- **Access control**: Only authenticated services can view process trees
- **Encryption**: All process attribution metadata encrypted at rest

## Testing Strategy

### Unit Tests
- **Fanotify initialization**: Verify event capture
- **PID resolution**: Test process tree traversal logic
- **Error handling**: Invalid PIDs, missing /proc entries

### Integration Tests
- **Real system**: Test on actual Linux workloads
- **Performance**: Validate throughput under load
- **Failure scenarios**: Process death during resolution

### End-to-End Tests
- **FIM workflow**: Complete FIM event → fanotify → process attribution
- **Cross-platform**: Optional Windows equivalent verification
- **Rollback scenarios**: Process fork/exec/fork handling

## Windows Equivalent (Optional)

### USN Journal Implementation
- **Technology**: Windows USN Journal API via minifilter driver
- **Alternatives**: EtW (Event Tracing for Windows) for process tracking
- **Complexity**: Higher than Linux fanotify, requires driver development

## Dependencies on Existing Systems

### FIM System Requirements
- **Event schema**: FIM events must contain resource path, tenant_id
- **Process metadata**: Support for additional event attributes
- **Tenant isolation**: Separate process attribution per tenant

### Autonomous Remediation Integration
- **Phase 64 dependency**: Use rotate_key playbook for credential rotation
- **Event flow**: FIM event → process attribution → autonomous remediation
- **Approval workflow**: Destructive actions require operator approval

## Implementation Complexity

### Low Complexity Items
- Basic fanotify initialization and event handling
- Simple PID resolution from /proc filesystem
- Basic process tree walking

### Medium Complexity Items
- Concurrent event handling under high load
- Integration with existing FIM database schema
- Error recovery and retry logic

### High Complexity Items
- Performance optimization for 10K+ events/second
- Multi-tenant isolation in cloud environments
- Cross-platform Windows implementation

## Success Metrics

### Technical Success
- **Detection**: 100% of FIM events have associated process tree
- **Latency**: Process attribution < 50ms per event
- **Uptime**: System availability > 99.9%

### Operational Success
- **MTTR**: < 15 minutes for process attribution failures
- **Scalability**: Handle 10x current load with optimizations
- **Compatibility**: Works with existing autonomous remediation workflows

## Implementation Timeline

### Week 1-2
- Core fanotify integration
- Basic PID resolution
- Simple process tree walking

### Week 3-4
- FIM schema integration
- Event correlation logic
- Basic error handling

### Week 5-6
- Performance optimization
- Testing and validation
- Production deployment preparation

### Week 7-8
- Windows equivalent (optional)
- Documentation and training
- Final integration testing
