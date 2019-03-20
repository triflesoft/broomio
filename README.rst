Broomio
=======

Fast async I/O module with many tradeoffs. Code is fast and thus often intentionally ugly and borderline unmaintanable.
Beauty of any kind is not priority for this project.
Specific trics:

1) All classes use __slots__

2) All validations are implented with "assert" statement, thus can be easily disabled in production with "-O" command line switch.

3) Some named constants are replaced with their values. To make code more readable this values are written as hexadecimal with "0x\_" prefix. See NOTES for specific cases.

