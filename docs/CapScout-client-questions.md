# CapScout: what we need from you

The customer meeting form is built and working. To finish the Banker and Connector meetings and the Zoho connection, we need the answers below. Short answers are fine. Where a question has a list to fill in, a table is provided.

## A. Banker meeting form

A Banker meeting is a visit to a banker. It is never converted into a Lead.

1. **Fields.** What should the sales manager fill in? Please list each field:

   | # | Field name | Type (text, number, date, dropdown, Yes/No) | If dropdown: the options | Required? |
   |---|---|---|---|---|
   | 1 | | | | |
   | 2 | | | | |
   | 3 | | | | |

2. **One page or steps?** Should it be one short page, or several steps like the customer form?
3. **Who is the banker?** Should we record the bank name, the banker's name, designation and mobile? Should a banker be saved so the next meeting with the same banker is quick to start?
4. **Zoho.** Should a Banker meeting be sent to Zoho? If yes, to which module (the Meetings module?), and what should the Title be?
5. **Where it shows in the app.** Under the Banker tab on the home screen only, or also somewhere else?

## B. Connector meeting form

A Connector is a person who refers customers to us. It is never converted into a Lead.

6. **Fields.** Same table as above, for connectors.

   | # | Field name | Type | If dropdown: the options | Required? |
   |---|---|---|---|---|
   | 1 | | | | |
   | 2 | | | | |
   | 3 | | | | |

7. **Link to customers.** The customer form has a "Referred By" field. Should it point to a saved connector, or stay as typed text?
8. **Zoho.** Same questions as for Banker (send to Zoho? which module? what Title?).
9. **One page or steps?**

## C. Zoho: decisions needed

10. **Real Zoho fields for the form answers.** Today only four answers go into real Zoho fields (Lead Name, Company, Mobile, City). The rest appear as text in the Lead's Description. We prepared a list of the 43 fields your Zoho admin would create to store every answer properly: *CapScout-Zoho-field-list.xlsx*. Do you want all of them, or only some? Which?
11. **Fields your operations team edits.** Which Lead fields does operations change directly in Zoho (for example status, owner, remarks)? The app will never overwrite those.
12. **Who shows as creator and owner in Zoho.** All records created by the app appear under the user the connection is set up with. Do you prefer a dedicated user such as "CapScout App", with each Lead and meeting owned by the real sales manager?
13. **Meeting Title in production.** In your production Meetings module the Title looks like a dropdown (for example "Customer"). If so, please send its options. The app will then use the Title for the type and put the MSME number elsewhere.
14. **Staff column.** Should the app fill the Staff column with the sales manager's name? Please send the field's API name.
15. **Field Sales Operator module.** What is its API name? Can a Mobile Number or Employee Code field be added to it? This lets each sales manager be matched to the right record without guessing from names.

## D. Process

16. **Prospects.** A customer is created in Zoho as a Lead only when the sales manager chooses Proceed. Before that, its meetings sit in the Meetings module with no Lead. Is this what you want?
17. **Dropped customers.** A customer whose Next Action is Dropped is left out of the home counts. Is this right? Should it also be hidden from the lists?
18. **Sales managers.** Please send the list for the real logins: full name, employee code, email and 10-digit mobile.

## E. What each sales manager sees when the app reads from Zoho

Later, once the production Zoho is connected, the app may read each sales manager's leads and meetings from Zoho instead of from its own database. Zoho holds a lot of older records, so we need rules for what to show.

19. **How far back?** By default, how far back should a sales manager see: from the go-live date only, or the last 30, 60 or 90 days?
20. **Older Leads.** Should Leads that were created in Zoho before the app existed appear for the sales manager, or only the ones created through the app?
21. **Older meetings.** The Meetings module already holds about 1,430 records, many of them entered by staff directly. Should these appear, or only meetings created through the app?
22. **Finished work.** Which Lead statuses mean "finished", so they are hidden from the main list? (A customer whose Next Action is Dropped is already left out of the home counts.)
23. **Never hide what needs action.** We suggest that follow-ups due today and overdue ones always show, whatever their age. Do you agree?
24. **Search.** Should the search box look across all of the sales manager's records, including older ones?

## F. Before we go live

25. **API limits.** What is the daily API credit limit of your production Zoho edition? Does the MCP server have its own limit?
26. **Go-live date,** and whether a pilot with 2 or 3 sales managers comes first.
