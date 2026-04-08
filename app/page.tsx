export default function Page() {
  return (
    <div style={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <iframe
        src="https://jjmswsmdailyreport-iddc2uqnaxvqcwm5j4zfhq.streamlit.app/?embed=true&embed_options=hide_footer&embed_options=hide_toolbar&embed_options=hide_padding"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "calc(100% + 50px)",
          border: "none",
        }}
      />
    </div>
  );
}
