import { NextResponse } from 'next/server';

export async function GET() {
  try {
    console.log('=== SMTP TEST STARTED ===');
    
    // Log all environment variables
    console.log('Process ENV Keys:', Object.keys(process.env).filter(k => k.includes('SMTP')));
    console.log('SMTP_HOST value:', process.env.SMTP_HOST);
    console.log('SMTP_PORT value:', process.env.SMTP_PORT);
    console.log('SMTP_USER value:', process.env.SMTP_USER);
    console.log('SMTP_PASS exists:', !!process.env.SMTP_PASS);
    console.log('SMTP_PASS length:', process.env.SMTP_PASS?.length);

    // Check if nodemailer is installed
    let nodemailer;
    try {
      nodemailer = require('nodemailer');
      console.log('Nodemailer imported successfully');
    } catch (e) {
      console.error('Nodemailer import failed:', e);
      return NextResponse.json(
        {
          status: 'error',
          message: 'Nodemailer not installed',
          error: e instanceof Error ? e.message : String(e),
        },
        { status: 500 }
      );
    }

    // Validate environment variables
    const envCheck = {
      SMTP_HOST: process.env.SMTP_HOST,
      SMTP_PORT: process.env.SMTP_PORT,
      SMTP_USER: process.env.SMTP_USER,
      SMTP_PASS_EXISTS: !!process.env.SMTP_PASS,
    };

    console.log('Environment check:', envCheck);

    if (!process.env.SMTP_HOST || !process.env.SMTP_USER || !process.env.SMTP_PASS) {
      console.warn('Missing SMTP configuration');
      return NextResponse.json(
        {
          status: 'error',
          message: 'Missing SMTP environment variables',
          environment: envCheck,
          allEnvKeys: Object.keys(process.env).sort(),
        },
        { status: 400 }
      );
    }

    // Try to create transporter
    console.log('Creating transporter...');
    const transporter = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: parseInt(process.env.SMTP_PORT || '587', 10),
      secure: parseInt(process.env.SMTP_PORT || '587', 10) === 465,
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS,
      },
      tls: {
        rejectUnauthorized: false,
      },
    });

    console.log('Transporter created, verifying connection...');
    
    // Test the transporter connection
    const verified = await transporter.verify();

    console.log('Verification result:', verified);

    if (verified) {
      return NextResponse.json(
        {
          status: 'success',
          message: 'SMTP connection verified successfully',
          config: {
            host: process.env.SMTP_HOST,
            port: process.env.SMTP_PORT,
            user: process.env.SMTP_USER,
          },
        },
        { status: 200 }
      );
    } else {
      return NextResponse.json(
        {
          status: 'error',
          message: 'SMTP connection could not be verified',
          config: {
            host: process.env.SMTP_HOST,
            port: process.env.SMTP_PORT,
            user: process.env.SMTP_USER,
          },
        },
        { status: 500 }
      );
    }
  } catch (error) {
    console.error('=== SMTP TEST ERROR ===', error);
    return NextResponse.json(
      {
        status: 'error',
        message: 'SMTP test failed',
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      },
      { status: 500 }
    );
  }
}
