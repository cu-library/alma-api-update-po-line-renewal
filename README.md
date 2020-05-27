# Alma API Tool - Update PO Line Renewal Date and Renewal Reminder Period

A command line tool to update the renewal date and reminder period for PO Line records in a set or for PO Line IDs provided as arguments.

```
Usage: po-line-renewal.py [OPTIONS] [PO_LINE_ID_ARGS]...

  PO Line Renewal - Bulk update the renewal date and renewal period for PO
  Lines in Alma

  A set-name or PO_LINE_ID_ARGS must be provided. If a set-name is provided,
  any PO_LINE_ID_ARGS provided as arguments are also processed.

  CAUTION: This version of the tool has an issue with dates and timezone
  handling. In some cases, the renewal date is set to the day before the one
  requested. Also, in some other cases, other date fields in the record
  (like Expected Activation Date) are set to a new value. The new value
  isn't being set explicitly by this tool. It is the old value of the field
  minus one day. This is either a bug in the Alma API itself or something
  this tool should work around.

Options:
  --set-name TEXT                 The identifier for the set of PO Lines we
                                  want to update

  --new-renewal-date TEXT         YYYY-MM-DD for the new renewal date
                                  [required]

  --new-renewal-period INTEGER RANGE
                                  The new renewal period
  --api-domain TEXT
  --api-key TEXT                  Alma API Key  [required]
  --help                          Show this message and exit.
```


