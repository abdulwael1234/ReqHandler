"""Port interface validators: interface-type matching for children.

Validates:
- interface_type ∈ {sender_receiver, client_server} (SRS-052)
- Children match parent interface_type (SRS-055)
- OperationArgument direction ∈ {input, output, input_output} (SRS-059)

See: LLD-02 §6.4 (Port Interface Validators)
"""
