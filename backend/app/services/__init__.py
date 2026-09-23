"""
External service integrations, one subpackage per dependency

Deliberately empty: a re-export here makes importing one service load every other one
That drags sqlalchemy and the adapters into modules that asked for none of them
"""
