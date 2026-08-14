console.log(Temporal.Now.plainDateTimeISO().toString());
console.log(new Date().toISOString().replace("T", " ").slice(0, 19));
console.log(Intl.DateTimeFormat().resolvedOptions().timeZone);
console.log(new Date().getTimezoneOffset());
console.log(new Date().toString());
console.log(process.env.TZ);
console.log(Temporal.Now.instant().toString());
console.log(Temporal.Now.instant().toString().replace("T", " ").slice(0, 19));
