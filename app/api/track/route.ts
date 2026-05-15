export async function POST(request: Request) {
  try {
    const body = await request.json();

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseSecretKey = process.env.SUPABASE_SECRET_KEY;

    if (!supabaseUrl || !supabaseSecretKey) {
      return Response.json(
        { error: "Missing Supabase environment variables" },
        { status: 500 }
      );
    }

    const payload = {
      page_url: body.page_url || "",
      referrer: body.referrer || "",
      user_agent: body.user_agent || "",
    };

    const response = await fetch(`${supabaseUrl}/rest/v1/visitor_logs`, {
      method: "POST",
      headers: {
        apikey: supabaseSecretKey,
        Authorization: `Bearer ${supabaseSecretKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return Response.json(
        { error: errorText },
        { status: response.status }
      );
    }

    return Response.json({ success: true });
  } catch (error) {
    return Response.json(
      { error: "Failed to track visit" },
      { status: 500 }
    );
  }
}
