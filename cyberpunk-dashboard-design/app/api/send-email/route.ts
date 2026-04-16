import { NextRequest, NextResponse } from 'next/server';
import { sendScoreEmail, sendWrapEmail } from '@/lib/email';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { type, username, email, ...data } = body;

    // Validate required fields
    if (!type || !email || !username) {
      return NextResponse.json(
        { error: 'Missing required fields: type, email, username' },
        { status: 400 }
      );
    }

    if (type === 'score') {
      // Send score email
      const { totalScore, shots, mode, date, averageScore } = data;

      if (!totalScore || !shots || !mode) {
        return NextResponse.json(
          { error: 'Missing required fields for score email: totalScore, shots, mode' },
          { status: 400 }
        );
      }

      const result = await sendScoreEmail({
        username,
        email,
        totalScore,
        shots,
        mode,
        date,
        averageScore,
      });

      return NextResponse.json(result, { status: 200 });
    } else if (type === 'wrap') {
      // Send wrap email
      const { summary, stats, date } = data;

      if (!summary || !stats) {
        return NextResponse.json(
          { error: 'Missing required fields for wrap email: summary, stats' },
          { status: 400 }
        );
      }

      const result = await sendWrapEmail({
        username,
        email,
        summary,
        stats,
        date,
      });

      return NextResponse.json(result, { status: 200 });
    } else {
      return NextResponse.json(
        { error: 'Invalid type. Must be "score" or "wrap"' },
        { status: 400 }
      );
    }
  } catch (error) {
    console.error('Email API error:', error);
    return NextResponse.json(
      {
        error: 'Failed to send email',
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}

// Health check endpoint
export async function GET() {
  return NextResponse.json(
    { message: 'Email API is running', status: 'ok' },
    { status: 200 }
  );
}
